# P11: Review and integration handoff

- PR: [#1 — adaptive cafeteria question engine](https://github.com/snuhcs-course/swpp-2026-project-team-11/pull/1)
- Target branch: `MVP`
- Work branch: `feat/p10-decision-tree-engine`
- P10 implementation completion: `f445778a5fb74a98f0458facb4a477c93d180c18`
- Default policy: `greedy`; optional experiment policy: `lookahead`
- Validation: 78 tests, Django checks, no pending migrations, and both smoke demos passed.
- [P10 GitHub test run](https://github.com/snuhcs-course/swpp-2026-project-team-11/actions/runs/37439828428) passed on Python 3.11.
- P12 teammate review and integration into `MVP` remain the next team step.

## Start working with this component

```bash
git fetch origin
git switch feat/p10-decision-tree-engine
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

The recorded paired benchmark shows a small question-count reduction and no
first-guess advantage for lookahead. Keep the default policy unless new shared
evaluation evidence supports a change. User acceptance and response likelihoods
still require calibration; the current report is a synthetic development check.
