# Group mode (i4-P3)

A group rarely agrees on one dish, so group mode recommends **restaurants**, two of
different character, and each member's own menu at each. Every round, each member answers a question chosen for them.
The package is pure Python + NumPy on top of the decision tree's intent model; the RL
and LLM engines are not used. There is no REST endpoint or client screen yet.

## Model

Each member keeps their own decision-tree intent belief `b_i(f)`, the probability that
menu `f` is the one they feel like (uniform over menus before any answer; the same
answer model as the single-user engine). Menus a member cannot eat (allergies, bans)
have belief 0 for that member only.

```text
P_i(r) = sum of b_i(f) over the menus f served at r     # i finds their menu at r
G(r)   = sum_i log P_i(r)                               # Nash welfare
```

`G(r)` is the log probability that every member finds their menu at `r`. A restaurant is
an offer's `restaurant` name, so `자하연식당>2층` and `>3층` are separate. Distance is not
part of the score. The first recommendation is `argmax G` and, for each member, the menu there
closest in expectation to the one they want (1 - mean absolute feature difference,
averaged over `b_i`). The likeliest menu would be arbitrary while `b_i` is still spread. A restaurant serving more menus starts with more probability: with no answer
it is the one recommended.

A second restaurant follows, the best other one under its own score:

| kind | score | meaning |
| --- | --- | --- |
| `balanced` | `sum_i log P_i(r)` | likely that everyone finds a menu |
| `no_one_unhappy` | `min_i P_i(r)` | the member least likely to find one is best served |

Questions and stopping use `G` only.

## Questions and stopping

For member `i` and question `q`, with the other members' beliefs fixed:

```text
gain(i, q) = sum_a P_i(a|q) max_r G_a(r)  -  max_r sum_a P_i(a|q) G_a(r)
```

Every member gets their highest-gain unasked question each round. When no single answer
can change the leading restaurant (all gains 0), the question that moves the leader's
margin most is asked. In the first round all members are alike, so they get the same question.

Another round is asked when the value of all members' answers together, enumerated over
every joint answer (`6^members`, hence at most 6 members), exceeds
`GroupConfig.question_cost` (.02 log-probability) per member asked. The first round is
always asked; `max_rounds` (4) caps the rest. A group whose menus come from one
restaurant gets it without a question. These constants are uncalibrated initial values.
Sums over a restaurant's menus are one matrix product, so a round over the 6,227 general
menus and 584 restaurants of a lunch takes about a second per member.

```python
from question_engines.group import GroupEngine

engine = GroupEngine(candidates, schema, excluded=[set(), {food_id_with_pork}])
while not engine.finished:
    for member, step in engine.questions().items():   # the round's unanswered questions
        engine.answer(member, step["question_id"], answer_id)
result = engine.recommendation()   # {"picks": [{"kind", "restaurant", "menus": [food or None per member]}], "rounds"}
```

## Benchmark

`benchmark_group` compares four arms on the same simulated members, each wanting one
target menu. A member's true satisfaction with a restaurant is the best feature
similarity to that target among its menus they can eat; the true group score is
`sum_i log(.05 + satisfaction_i)`.

- `group`: this engine.
- `separate`: each member's own `preference` session until it would propose a menu
  (at most 20 questions, as in the engine benchmark), then `argmax G` over their beliefs.
- `separate_matched`: the same, capped at the group's number of rounds per member.
- `most_menus`: the restaurant with the most menus, without a question.

Every arm makes two picks the same way (`most_menus` from equal beliefs over all menus,
so its picks are the two largest restaurants). The criteria judge the first pick;
`picks` reports each one's regret and mean and least satisfaction, and
`best_pick_regret_per_member` the regret if the group chose the truly better of the two.

Situations are `similar` (targets among each other's ten nearest menus), `conflict`
(far-apart targets) and `restricted` (one member has one of pork, wheat, milk or egg,
when a menu without it exists), each with groups of 2, 3 and 5. Results are per
situation, never averaged across them: the share of groups given the truly best
restaurant, Nash regret per member, the least satisfied member, the mean similarity of the
menus members are told (each arm picks them as the engine does), total questions and rounds.

**Pass criteria** (`evaluation.py`). In every situation:

1. `group` asks at most half the questions of `separate` (mean total per group).
2. `group`'s mean Nash regret per member exceeds `separate`'s by at most .02, about
   2% lower geometric-mean satisfaction.
3. `group`'s mean regret per member is below `separate_matched`'s: with the same number
   of questions, choosing them for the group beats each member's own questions.
4. `group`'s mean regret per member is below `most_menus`'s.

Criteria 1–3 were fixed before the first run; criterion 4 was added after it, before
the second case sets were frozen.

```bash
python manage.py benchmark_group --date 2026-11-10 --dir DIR                   # freezes DIR/cases.json; commit it
python manage.py benchmark_group --date 2026-11-10 --dir DIR                   # ResponseOracle members, no key
python manage.py benchmark_group --date 2026-11-10 --dir DIR --simulator llm   # LLM members (paid)
python manage.py benchmark_group --source general --dir DIR2 ...               # the restaurants near the stations
```

The first run freezes 6 cases per situation and size (54) from the menus and `--seed`, and
stops. Later runs refuse menus that differ from the frozen ones. The LLM members are the
engine benchmark's simulated user (`METCHU_SIMULATOR_MODEL`), told only the target's name;
their answers are cached in `DIR/answers.jsonl`, shared by the arms. Similarity and the
answer model come from the same features, so absolute satisfaction is optimistic; the
comparison between arms is what the criteria judge. Taking the best menu of a restaurant
also favors restaurants with many menus, which `most_menus` makes visible.

## Results

### First version: preference fit (2026-11-10, 11/02 lunch)

The first version scored `U_i(r)` as the best preference fit (`PreferencePlanner.fit`,
normalized over the answered features) and `G(r) = sum_i log(.05 + U_i(r))`. Results are
in `engine_benchmark_results/group-2026-11-02/` (`llm.json` with `openai:gpt-6-luna`,
prompt `45d1d4125724`, 846 calls; `oracle.json`). **It failed every situation with both
simulators.** It met criterion 1, but not criterion 2, and criterion 3 only for
`restricted` with the oracle.

| LLM members, mean | similar | conflict | restricted |
| --- | ---: | ---: | ---: |
| questions: group / separate | 4.4 / 21.4 | 6.9 / 21.4 | 8.1 / 21.9 |
| regret per member: group / separate / matched | .183 / .023 / .074 | .056 / .002 / .028 | .037 / .021 / .026 |
| truly best restaurant: group / separate | 11% / 72% | 39% / 83% | 50% / 56% |

Replaying the cached answers showed why. After one shared YES (often "something served
hot") every member's fit was about .95 at many restaurants. Their Nash welfare tied, the
next round looked worthless and the group stopped (19 of 54 LLM groups after one round);
the tie went to the first name in sorted order (동원관식당, 21 of 54). The separate arms
then aggregated fits too; they now aggregate beliefs like the group.

The current belief version was checked on those already-seen cases with oracle members
before new cases were frozen. A prior that is uniform over restaurants instead of menus
was tried there and dropped: it failed every check in every situation.

### Belief version (2026-11-11, 11/10 lunch)

Menus come from a copy of the live server's food DB taken 2026-11-10 23:27 (release
`local-hours-fab28cd3fe36`; kept outside Git): 244 cafeteria menus at 22 restaurants,
and 6,227 general menus at 584 restaurants. The live release also filters general
menus by opening hours (4,227 at lunch); `main` does not yet. Results are in
`engine_benchmark_results/group-2026-11-10-cafeteria/` and `-general/`; LLM members
used `openai:gpt-6-luna`, prompt `45d1d4125724` (1,066 and 1,832 calls).

| Passed situations | cafeteria | general |
| --- | --- | --- |
| LLM members | all three | conflict, restricted (similar fails criterion 2) |
| oracle members | similar, conflict (restricted fails 3) | none (similar fails 2; conflict, restricted fail 3) |

| LLM members, mean | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| questions: group / separate | 4.2 / 21.7 | 8.0 / 23.7 | 6.6 / 24.2 | 9.3 / 32.8 | 11.8 / 34.0 | 10.3 / 33.2 |
| regret per member: group | .017 | .007 | .008 | .062 | .040 | .039 |
| separate / matched / most menus | .004 / .048 / .096 | .005 / .020 / .010 | .006 / .018 / .154 | .033 / .080 / .090 | .024 / .046 / .069 | .024 / .049 / .077 |

Group mode asks 21–35% of the questions of separate sessions, and with the same number
of questions it chooses better than they do in every LLM situation. Each situation has
18 groups: most differences from `separate` and `separate_matched` lie within their
95% intervals, so criteria 2 and 3 pass on point estimates, not as established effects.
In the cafeteria the restaurant with the most menus (220동식당) is the group's choice in
34 of 54 groups, and 30 groups stop after one round.

These results predate two fixes found by reading the general cases. Members were told
their likeliest menu at the restaurant (a 술국 lover was told 한돈 족발한상), which no
criterion scored; they are now told the closest menu, and `menu_satisfaction` reports it.
Three general `similar` groups had two members with the same target, because a menu with
a twin of identical features could be drawn as its own neighbour. Asking more rounds was
also checked on these cases with oracle members: a question cost of .005 or .001 instead
of .02 adds 1–3 questions per group and changes regret by at most .008 per member, so
the cost stays.

### Two picks (dev check, already-seen 11/10 cases, oracle members)

On the cases above, before any new freeze, with oracle members (regret per member):

| | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| group: `balanced` / `no_one_unhappy` | .024 / .090 | .009 / .027 | .022 / .171 | .055 / .071 | .061 / .042 | .051 / .044 |
| group: better of the two | .009 | .005 | .000 | .039 | .037 | .031 |
| `most_menus`: better of the two | .016 | .005 | .150 | .057 | .045 | .042 |

In general `conflict` and `restricted` groups the `no_one_unhappy` pick beats `balanced` in
regret, and in `conflict` also in its least satisfied member (.845 against .813). In the
cafeteria it is mostly the 75-1동 food court (41 of 54 groups) and does worse. A third
pick was tried and dropped: `sum_i P_i(r)` never beat `balanced`, even in mean
satisfaction. Replayed on the cached LLM answers, a menu-count-normalized "specialty" score chose specialties of the
wrong dish (스키야키 for two 시샤모 lovers) and did worse in every situation.
