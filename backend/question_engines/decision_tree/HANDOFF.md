# P11: Review and integration handoff

- PR: [#11 — feature-aware recommendation and question policy](https://github.com/snuhcs-course/swpp-2026-project-team-11/pull/11)
- Work branch: `feat/i2-p11-dt-feature-integration`
- Temporary target: `feat/i2-p11-feature-extractor` (extractor PR #10).
- Merge order: preprocessing #5, extractor #10, then this PR. Retarget #11 to
  `MVP` after #10 merges; do not merge into the temporary feature base.
- Default policy: `preference` (configurable via `METCHU_DT_POLICY=preference|greedy|lookahead`); reference policies: `greedy`, `lookahead`.
- Engine policy version: `decision-tree.3.0`; older session snapshots are rejected.
- Local validation: 297 backend tests passed. The 10/13 failure
  is covered by a regression fixture, 24-trial `ResponseOracle` simulated-user comparisons, and local browser flow verification.
- Original P10 implementation and benchmark remain documented in the README.

## Start working with this component

```bash
git fetch origin
git switch feat/i2-p11-dt-feature-integration
python -m pip install -r backend/requirements.txt
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-09-29
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU --smoke
```

Activate your local Python environment first. The fixture date is required;
September 29 lunch supplies 193 candidates and 23 features. Engine development
and smoke tests need no API key. See the [full API contract](README.md) for
candidate fields, answer IDs, step shapes, replay, and model assumptions.

## Team integration responsibilities

| Task | Owner | Ready-to-use handoff |
| --- | --- | --- |
| P17 shared interface | Bonjae Ku | Wrap `DecisionTreeEngine`; preserve question/guess IDs and the six answer IDs |
| P19 UI integration | Bonjae Ku | Render `question`, `guess`, `recommendation`, and `unavailable`; distinguish group guesses from final concrete foods |
| P20 integration testing | Bonjae Ku | Use smoke/benchmark commands and `diagnostics()`; record actual user acceptance separately from synthetic matching |
| P13/P14 LLM engine | Seungho Lee | Use the same dated candidate list and align output rendering through P17 |
| P5–P7 menu pipeline | Shinseo Kim | Existing `menus.services` and fixture are consumed unchanged; schema changes invalidate snapshots |
| P12 review/P21 demo coordination | Mingyu Lee with the team | Review the PR, integrate the shared interface and client, then verify both MVPs against one snapshot |

The engine is one session per instance. The shared backend wrapper supplies
session IDs, storage, locking, revisions, and idempotency. A final recommendation
contains a real input `food_id` and original cafeteria offers. The component's
smoke demo does not establish that the complete Android MVP is integrated.

The historical paired benchmark compares the two intent-based reference policies.
The default preference policy instead ranks concrete foods by signed explicit
preferences and uses local expected decision value to select questions and stop.
The October 13 regression ends in nine questions under the new ordering, versus
the recorded fifteen-question failure; the newly asked spicy question is UNKNOWN
in that test. These regression checks do not establish human acceptance rates.
Question cost, response likelihoods, and preference strengths still need user
calibration. See the README for the two-step approximation and its limits.
