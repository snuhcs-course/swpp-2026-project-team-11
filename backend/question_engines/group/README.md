# Group mode (i4-P3)

A group rarely agrees on one dish, so group mode recommends one **restaurant** and each
member's own menu there. Every round, each member answers a question chosen for them.
The package is pure Python + NumPy on top of the decision tree's `preference` model;
the RL and LLM engines are not used. There is no REST endpoint or client screen yet.

## Model

Each member keeps their own decision-tree state: the intent belief that forecasts their
answers, and the preference fit `u_i(f)` in [0,1] of every menu (`PreferencePlanner.fit`).
Menus a member cannot eat (allergies, bans) have fit 0 for that member only.

```text
U_i(r) = max over menus f served at r of u_i(f)
G(r)   = sum_i log(EPSILON + U_i(r))        # Nash welfare, EPSILON = .05
```

A restaurant is an offer's `restaurant` name, so `자하연식당>2층` and `>3층` are separate.
Distance is not part of the score. The recommendation is `argmax G` (ties go to the first
name in sorted order) and, for each member, their best menu there.

## Questions and stopping

For member `i` and question `q`, with the other members' scores fixed:

```text
gain(i, q) = sum_a P_i(a|q) max_r G_a(r)  -  max_r sum_a P_i(a|q) G_a(r)
```

Every member gets their highest-gain unasked question each round. When no single answer
can change the leading restaurant (all gains 0), the question that moves the leader's
margin most is asked. In the first round all members are alike, so they get the same question.

Another round is asked when the value of all members' answers together, enumerated over
every joint answer (`6^members`, hence at most 6 members), exceeds
`GroupConfig.question_cost` (.02 Nash units) per member asked. The first round is always
asked; `max_rounds` (4) caps the rest. A group whose menus come from one restaurant gets
it without a question. These constants are uncalibrated initial values.

```python
from question_engines.group import GroupEngine

engine = GroupEngine(candidates, schema, excluded=[set(), {food_id_with_pork}])
while not engine.finished:
    for member, step in engine.questions().items():   # the round's unanswered questions
        engine.answer(member, step["question_id"], answer_id)
result = engine.recommendation()   # {"restaurant", "menus": [food or None per member], "rounds"}
```

## Benchmark

`benchmark_group` compares three arms on the same simulated members, each wanting one
target menu. A member's true satisfaction with a menu is its feature similarity to that
target (0 for a menu they cannot eat).

- `group`: this engine.
- `separate`: each member's own `preference` session until it would propose a menu
  (at most 20 questions, as in the engine benchmark), then the same Nash choice over
  their fits.
- `separate_matched`: the same, capped at the group's number of rounds per member.

Situations are `similar` (targets among each other's ten nearest menus), `conflict`
(far-apart targets) and `restricted` (one member has one of pork, wheat, milk or egg,
when a menu without it exists), each with groups of 2, 3 and 5. Results are per
situation, never averaged across them: the share of groups given the truly best
restaurant, Nash regret per member, the least satisfied member, total questions and rounds.

**Pass criteria**, fixed before the first run (`evaluation.py`). In every situation:

1. `group` asks at most half the questions of `separate` (mean total per group).
2. `group`'s mean Nash regret per member exceeds `separate`'s by at most .02, about
   2% lower geometric-mean satisfaction.
3. `group`'s mean regret per member is below `separate_matched`'s: with the same number
   of questions, choosing them for the group beats each member's own questions.

```bash
python manage.py benchmark_group --date 2026-11-02 --dir DIR                  # freezes DIR/cases.json; commit it
python manage.py benchmark_group --date 2026-11-02 --dir DIR                  # ResponseOracle members, no key
python manage.py benchmark_group --date 2026-11-02 --dir DIR --simulator llm  # LLM members (paid)
```

The first run freezes 6 cases per situation and size (54) from the menu and `--seed`, and
stops. Later runs refuse a menu that differs from the frozen one. The LLM members are the
engine benchmark's simulated user (`METCHU_SIMULATOR_MODEL`), told only the target's name;
their answers are cached in `DIR/answers.jsonl`, shared by the three arms. Similarity
and fit come from the same features, so absolute satisfaction is optimistic; the
comparison between arms is what the criteria judge.
