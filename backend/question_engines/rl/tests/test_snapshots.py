"""Current policy contracts, independent of any frozen v20 question trace."""
import copy
import json
import numpy as np
import pytest
from menus.personal.catalog import canonical_foods
from question_engines.rl import RLEngine
from question_engines.rl.policy import FEATURE_KEYS, MANIFEST


def menu():
    rows=copy.deepcopy(list(canonical_foods().values())[:12])
    for row in rows:row['offers']=[{'restaurant':'Hall','meal':'LU','price':5000}]
    return rows


def test_model_manifest_and_dynamic_candidates():
    assert MANIFEST['parameters']==562123
    for count in [1,12,267]:
        rows=copy.deepcopy(list(canonical_foods().values())[:count])
        e=RLEngine(rows)
        assert e.start()['type']==('guess' if count==1 else 'question')
        e.recommend_now();assert e.next_step()['type']=='guess'


def test_restore_and_undo_preserve_pending_choices_and_rng():
    rows=menu();engine=RLEngine(rows,language='ko')
    q=engine.start();engine.answer(q['question_id'],'probably_yes')
    first=engine.recommend_now();engine.feedback(first['guess_id'],False)
    engine.recommend_now()
    snapshot=json.loads(json.dumps(engine.snapshot()));restored=RLEngine.from_snapshot(rows,snapshot)
    assert restored.next_step()==engine.next_step()
    assert restored.snapshot()==snapshot
    while engine.can_undo:assert restored.undo()==engine.undo()
    assert restored.next_step()==q


def test_twenty_requests_switch_to_offer_only_and_rejections_are_never_repeated():
    rows=menu();engine=RLEngine(rows)
    # Independent adversarial user: every proposal is rejected; every attribute
    # answer is uninformative. No simulator's acceptance assumptions are involved.
    proposed=set()
    for _ in range(80):
        step=engine.next_step()
        if step['type']=='unavailable':break
        if engine.requests>=20:assert step['type']=='guess'
        if step['type']=='question':engine.answer(step['question_id'],'unknown')
        else:
            assert step['food']['food_id'] not in proposed
            proposed.add(step['food']['food_id']);engine.feedback(step['guess_id'],False)
    assert len(proposed)==len(rows)
    assert engine.next_step()['type']=='unavailable'


def test_new_campus_candidate_is_not_classified_and_offer_count_does_not_change_prior():
    rows=menu();campus=copy.deepcopy(rows[0]);campus.pop('canonical_id');campus['food_id']=11;campus['name']='New campus meal'
    a=RLEngine(rows+[campus]);b=RLEngine([{**rows[0],'offers':rows[0]['offers']*50},*rows[1:],campus])
    assert np.array_equal(a.world.prior.numpy(),b.world.prior.numpy())
    assert a._foods[-1]['name']=='New campus meal'
    assert a.world.prior[-1]>0


def test_masks_and_catalogue_permutation():
    rows=menu();a=RLEngine(rows);b=RLEngine(rows[::-1])
    answers=np.full(53,-1,dtype=np.int8);answers[0]=0
    pa,_=a.world.probabilities(answers,np.zeros(12,dtype=bool));pb,_=b.world.probabilities(answers,np.zeros(12,dtype=bool))
    assert np.allclose(pa['acceptance_probability'].numpy(),pb['acceptance_probability'].numpy()[:,::-1],atol=1e-6)


def test_restore_rejects_foreign_policy_and_catalogue():
    rows=menu();e=RLEngine(rows);s=e.snapshot()
    for change in [{'engine_version':'old'}, {'pending':['guess',-1]}]:
        with pytest.raises(ValueError):RLEngine.from_snapshot(rows,s|change)
    with pytest.raises(ValueError):RLEngine.from_snapshot(rows[::-1],s)
