"""Frozen 53-feature personal policy. CPU inference; no training runtime imports."""
import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import threading

import numpy as np

from menus.features.schema import FEATURE_KEYS, MODEL_LABELS

ASSETS = Path(__file__).with_name('assets')
MANIFEST = json.loads((ASSETS/'manifest.json').read_text(encoding='utf-8'))
MODEL_VERSION = MANIFEST['version']
CHECKPOINT_SHA256 = MANIFEST['checkpoint_sha256']
_lock = threading.Lock()

@lru_cache(maxsize=1)
def model():
    import torch
    from .neural import PosteriorDialogueModel
    with _lock:
        if list(MODEL_LABELS) != MANIFEST["feature_keys"]:
            raise ValueError("The feature order differs from the frozen model")
        if hashlib.sha256((ASSETS/'weights.npz').read_bytes()).hexdigest() != MANIFEST['weights_sha256']:
            raise ValueError('Personal model checksum mismatch')
        torch.set_num_threads(1)
        network = PosteriorDialogueModel().cpu().eval()
        with np.load(ASSETS/'weights.npz') as data:
            state = {k:torch.from_numpy(data[k].copy()) for k in data.files if k!='food_prior'}
            prior = data['food_prior'].copy()
        network.load_state_dict(state, strict=True)
        for parameter in network.parameters():parameter.requires_grad_(False)
        return network, prior


def prepare(rows):
    return PreparedCatalog(rows)


class PreparedCatalog:
    def __init__(self, rows):
        import torch
        self.network, priors = model()
        n, f = len(rows), len(FEATURE_KEYS)
        means, deviations, masks = [], [], []
        for row in rows:
            values, std = row.get('features'), row.get('feature_std')
            if not isinstance(values,dict) or not isinstance(std,dict):raise ValueError('Mean and std dictionaries are required')
            if set(values)!=set(FEATURE_KEYS) or set(std)!=set(FEATURE_KEYS):
                raise ValueError('The personal model requires the complete v3 schema')
            if any((values[k] is None)!=(std[k] is None) for k in FEATURE_KEYS):raise ValueError("Unknown mean/std must both be null")
            known=np.array([values[k] is not None and std[k] is not None for k in FEATURE_KEYS])
            m=np.array([values[k] if known[i] else 0. for i,k in enumerate(FEATURE_KEYS)],dtype=np.float32)
            s=np.array([std[k] if known[i] else 0. for i,k in enumerate(FEATURE_KEYS)],dtype=np.float32)
            if not np.isfinite(m).all() or not np.isfinite(s).all() or (m<0).any() or (m>1).any() or (s<0).any() or (s>.5).any() or (s*s>m*(1-m)+1e-6).any():
                raise ValueError('Invalid personal feature moments')
            means.append(m);deviations.append(s);masks.append(known)
        mean=np.asarray(means);std=np.asarray(deviations);mask=np.asarray(masks)
        # New campus menus retain their own features and identity. Their prior is
        # smoothly transferred from eight nearest known sensory profiles; no new
        # menu is classified into a canonical category to enter the candidate pool.
        with (ASSETS/'foods.csv').open(encoding='utf-8-sig') as file:reference=list(csv.DictReader(file))
        labels=MANIFEST['feature_keys']
        rm=np.array([[float(row[k+'_mean']) if row[k+'_mean'] else .5 for k in labels] for row in reference])
        rk=np.array([[row[k+'_mask']=='1' for k in labels] for row in reference])
        lookup={key:i for i,key in enumerate(MANIFEST['food_ids'])}
        assigned=[]
        for i,row in enumerate(rows):
            if row.get('canonical_id') in lookup:assigned.append(priors[lookup[row['canonical_id']]])
            else:
                common=rk & mask[i];count=common.sum(1)
                distance=(abs(rm-mean[i])*common).sum(1)/np.maximum(count,1)
                distance[count==0]=np.inf
                indices=np.argsort(distance,kind='stable')[:8]
                weights=np.exp(-8*distance[indices]);den=weights.sum()
                assigned.append(float(weights@priors[indices]/den) if den else float(np.median(priors)))
        self.mean=torch.from_numpy(mean);self.std=torch.from_numpy(std);self.mask=torch.from_numpy(mask)
        self.prior=torch.tensor(assigned,dtype=torch.float32)
        self.numeric_fingerprint=hashlib.sha256(mean.tobytes()+std.tobytes()+mask.tobytes()+self.prior.numpy().tobytes()).hexdigest()
        value=.5+(mean-.5)*(1-4*std**2).clip(0)*mask
        direction=np.stack([value*.68+(1-value)*.02,value*.24+(1-value)*.06,value*.06+(1-value)*.24,value*.02+(1-value)*.68],-1)
        channel=np.empty((n,f,6),dtype=np.float32);channel[:,:,[0,1,3,4]]=direction*.72;channel[:,:,2]=.18;channel[:,:,5]=.10
        self.channel=torch.from_numpy(channel.transpose(1,2,0).copy())
        self.entropy=-(self.channel*self.channel.log()).sum(1).T.contiguous()

    def probabilities(self, answers, rejected):
        import torch
        with torch.inference_mode():
            a=torch.from_numpy(np.asarray(answers,dtype=np.int64)+1)[None]
            feedback=torch.from_numpy(np.asarray(rejected,dtype=np.int64))[None]
            return self.network.predictor(self.mean,self.std,self.mask,self.prior,a,feedback),a

    def decide(self, answers, rejected, *, requests=0, offers=0, force=False, rng=None, **unused):
        import torch
        rng = rng if rng is not None else np.random.default_rng()
        with torch.inference_mode():
            pred,a=self.probabilities(answers,rejected)
            p=pred['acceptance_probability'];best=int(p[0].argmax())
            scores=p[0].numpy().copy()
            if force or requests>=20 or (a!=0).all():return -1,best,scores
            normalized=p/p.sum(-1,keepdim=True).clamp_min(1e-9)
            resp=torch.einsum('bn,fan->bfa',normalized,self.channel)
            entropy=-(resp*resp.clamp_min(1e-8).log()).sum(-1)
            mi=(entropy-normalized@self.entropy).clamp_min(0)
            numerator=torch.einsum('bn,fan->bfa',normalized.square(),self.channel.square())
            branch=numerator/resp.square().clamp_min(1e-10)
            expected=(branch*pred['response_probability']).sum(-1)
            concentration=(expected/normalized.square().sum(-1,keepdim=True).clamp_min(1e-12)).clamp_min(1).log()
            gain=(.7123647*mi+.2876353*concentration).clamp_min(0)*(a==0)
            top=normalized.max(-1).values
            threshold=.26617*(top/(1-top).clamp_min(1e-7)).pow(.7156705)
            dt=gain.max(-1).values<=threshold
            out=self.network.policy(pred,gain,a==0,torch.tensor([float(requests)]),torch.tensor([float(offers)]),dt)
            modes=out['action_probabilities'][0].numpy().astype(float);modes/=modes.sum()
            mode=int(rng.choice(2,p=modes))
            if mode:return -1,best,scores
            prob=out['question_probabilities'][0].numpy().astype(float);prob/=prob.sum()
            return int(rng.choice(len(FEATURE_KEYS),p=prob)),best,scores

    def refusal_row(self,index):
        return np.zeros(len(self.mean))
