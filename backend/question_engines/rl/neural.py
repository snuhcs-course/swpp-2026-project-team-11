"""Frozen predictor and dialogue policy definitions for CPU inference.

Food choice is argmax acceptance probability and has no PPO parameters.
Predictor inputs contain public answers/feedback and catalogue values only;
question order, policy logits, simulated persona and target IDs are absent.
"""
import math
import torch
from torch import nn
from torch.nn import functional as F

class PreferencePredictor(nn.Module):
 def __init__(self,features=53,hidden=128,heads=4,layers=2,ff=256,response_prior=None):
  super().__init__();self.features=features;self.hidden=hidden
  self.feature_embedding=nn.Embedding(features,hidden)
  self.answer_embedding=nn.Embedding(7,hidden)
  self.input_norm=nn.LayerNorm(hidden)
  layer=nn.TransformerEncoderLayer(hidden,heads,ff,dropout=0.,activation='gelu',batch_first=True,norm_first=True)
  self.context=nn.TransformerEncoder(layer,layers,enable_nested_tensor=False)
  self.context_norm=nn.LayerNorm(hidden)
  self.food_encoder=nn.Sequential(nn.Linear(features*3,hidden),nn.LayerNorm(hidden),nn.GELU(),nn.Linear(hidden,hidden),nn.GELU())
  self.history_fusion=nn.Sequential(nn.Linear(hidden*3+3,hidden),nn.LayerNorm(hidden),nn.GELU())
  self.food_attention=nn.MultiheadAttention(hidden,heads,dropout=0.,batch_first=True)
  self.food_context_norm=nn.LayerNorm(hidden)
  self.response_head=nn.Sequential(nn.Linear(hidden*2,hidden),nn.GELU(),nn.Linear(hidden,6))
  self.acceptance_head=nn.Sequential(nn.Linear(hidden*3,hidden),nn.GELU(),nn.Linear(hidden,1))
  prior=torch.full((features,6),1/6) if response_prior is None else torch.as_tensor(response_prior,dtype=torch.float32)
  if prior.shape!=(features,6) or not torch.isfinite(prior).all() or (prior<0).any() or (prior.sum(-1)<=0).any():raise ValueError('invalid response prior')
  prior=prior.clamp_min(1e-8);prior=prior/prior.sum(-1,keepdim=True)
  self.response_baseline=nn.Parameter(prior.log())
  self.evidence_gain=nn.Parameter(torch.tensor(math.log(math.expm1(2.))))
  self.register_buffer('answer_strength',torch.tensor([0.,1.,.5,0.,-.5,-1.,0.]))
  for head in [self.response_head,self.acceptance_head]:nn.init.zeros_(head[-1].weight);nn.init.zeros_(head[-1].bias)
 def forward(self,mean,std,mask,food_prior,answers,feedback):
  # Shared catalogue [foods, features]; per-session public state [batch,...].
  if mean.ndim!=2 or mean.shape[0]<1 or mean.shape[1]!=self.features:raise ValueError('catalogue shape')
  b,f=answers.shape;n=mean.shape[0]
  if std.shape!=mean.shape or mask.shape!=mean.shape or food_prior.shape!=(n,) or feedback.shape!=(b,n) or f!=self.features:raise ValueError('state shape')
  known=mask.bool();fm=torch.where(known,mean,0.);fs=torch.where(known,std,0.)
  foods=self.food_encoder(torch.cat([fm,fs,known.to(mean.dtype)],-1))
  q=self.feature_embedding.weight[None]+self.answer_embedding(answers)
  q=self.context_norm(self.context(self.input_norm(q)))
  def feedback_pool(code):
   w=(feedback==code).to(mean.dtype);return w@foods/w.sum(-1,keepdim=True).clamp_min(1.)
  observed=(answers!=0);counts=torch.stack([observed.sum(-1)/self.features,(feedback==1).sum(-1)/max(n,1),(feedback==2).sum(-1)/max(n,1)],-1)
  user=self.history_fusion(torch.cat([q.mean(1),feedback_pool(1),feedback_pool(2),counts],-1))
  memory=torch.cat([q,user[:,None,:]],1)
  # The summary token is always valid, including an empty dialogue.
  padding=torch.cat([~observed,torch.zeros(b,1,dtype=torch.bool,device=mean.device)],-1)
  food=foods[None].expand(b,-1,-1)
  attended,_=self.food_attention(food,memory,memory,key_padding_mask=padding,need_weights=False)
  local=self.food_context_norm(food+attended)
  logits=self.acceptance_head(torch.cat([food,local,user[:,None,:].expand(-1,n,-1)],-1)).squeeze(-1)
  strengths=self.answer_strength[answers];reliability=(1-4*fs.square()).clamp_min(0)*known
  evidence=strengths@((2*fm-1)*reliability).T/strengths.abs().sum(-1,keepdim=True).clamp_min(1.)
  logits=logits+torch.logit(food_prior.clamp(1e-6,1-1e-6))[None]+F.softplus(self.evidence_gain)*evidence
  available=feedback==0;probability=logits.sigmoid()*available
  response=self.response_baseline[None]+self.response_head(torch.cat([q,user[:,None,:].expand(-1,f,-1)],-1))
  return {'acceptance_logits':logits,'acceptance_probability':probability,'response_logits':response,'response_probability':response.softmax(-1),'question_context':q,'user_context':user,'food_available':available}

class DialoguePolicy(nn.Module):
 def __init__(self,hidden=128):
  super().__init__();self.question_head=nn.Sequential(nn.Linear(hidden*2+2,64),nn.GELU(),nn.Linear(64,1));self.action_head=nn.Sequential(nn.Linear(hidden+8,hidden),nn.GELU(),nn.Linear(hidden,2));self.value_head=nn.Sequential(nn.Linear(hidden+8,hidden),nn.GELU(),nn.Linear(hidden,1));self.dt_action_strength=nn.Parameter(torch.tensor(math.log(9.)))
  for head in [self.question_head,self.action_head,self.value_head]:nn.init.zeros_(head[-1].weight);nn.init.zeros_(head[-1].bias)
 def forward(self,prediction,question_gain,question_available,requests,offer_count,dt_recommends,temperature=1.):
  if temperature<=0:raise ValueError('temperature must be positive')
  # Detach at the module boundary: policy gradients cannot reach predictors.
  user=prediction['user_context'].detach();q=prediction['question_context'].detach();p=prediction['acceptance_probability'].detach();food_available=prediction['food_available'];gain=question_gain.detach();valid=question_available.bool();b,f=valid.shape
  residual=self.question_head(torch.cat([q,user[:,None].expand(-1,f,-1),gain[:,:,None],valid.to(q.dtype)[:,:,None]],-1)).squeeze(-1)
  base=gain.clamp_min(1e-8).log();qlogits=((base+residual)/temperature).masked_fill(~valid,-1e9);qprob=qlogits.softmax(-1)*valid;qprob=qprob/qprob.sum(-1,keepdim=True).clamp_min(1e-9)
  best=p.max(-1).values;ordered=p.topk(min(2,p.shape[1]),-1).values;gap=best-(ordered[:,1] if ordered.shape[1]>1 else torch.zeros_like(best));normalized=p/p.sum(-1,keepdim=True).clamp_min(1e-9);entropy=-(normalized*normalized.clamp_min(1e-9).log()).sum(-1)
  stats=torch.stack([best,gap,p.mean(-1),gain.masked_fill(~valid,0).max(-1).values,valid.float().mean(-1),requests/20,offer_count/20,entropy],-1);context=torch.cat([user,stats],-1)
  raw=self.action_head(context)+F.one_hot(dt_recommends.long(),2)*self.dt_action_strength
  has_food=food_available.any(-1);has_question=valid.any(-1);within_cap=requests<20
  allowed=torch.stack([has_question&has_food,has_food&(requests>0)],-1)&within_cap[:,None]
  action_logits=raw.masked_fill(~allowed,-1e9);action_prob=action_logits.softmax(-1)*allowed;action_prob=action_prob/action_prob.sum(-1,keepdim=True).clamp_min(1e-9)
  # No actor-food head and no food softmax sampling: select exactly the best
  # available acceptance prediction. The index is not a trainable quantity.
  food_index=p.masked_fill(~food_available,-torch.inf).argmax(-1);food_index=torch.where(has_food&within_cap,food_index,-1)
  return {'question_probabilities':qprob,'action_probabilities':action_prob,'food_index':food_index,'value':self.value_head(context).squeeze(-1),'terminal':~allowed.any(-1)}

class PosteriorDialogueModel(nn.Module):
 def __init__(self,response_prior=None):
  super().__init__();self.predictor=PreferencePredictor(response_prior=response_prior);self.policy=DialoguePolicy()
