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
fit_i(r, f) = similarity of f to the closest menu at r that i can eat   # 0 if there is none
S_i(r)      = sum_f b_i(f) fit_i(r, f)                                  # i's expected satisfaction at r
G(r)        = sum_i log S_i(r)                                          # Nash welfare
```

Similarity is 1 - mean absolute feature difference, as in the benchmark: a menu like the
one a member wants counts for most of a match. An earlier version scored the probability
`P_i(r)` that the wanted menu itself is served, which only counts menus and favored the
largest restaurants. A restaurant is an offer's `restaurant` name, so `자하연식당>2층` and
`>3층` are separate. Distance is not part of the score. The first recommendation is
`argmax G` and, for each member, the menu there closest in expectation to the one they
want (similarity averaged over `b_i`). The likeliest menu would be arbitrary while `b_i`
is still spread. The `fit` table of a catalog takes about 3 s for the 6,227 general
menus and is cached per catalog and excluded menus.

A second restaurant follows, the best other one under its own score. Every pick is a
restaurant with a menu for every member; a kind with no such restaurant left is omitted,
and a group that no restaurant can serve is rejected:

| kind | score | meaning |
| --- | --- | --- |
| `balanced` | `sum_i log S_i(r)` | everyone is satisfied in balance |
| `no_one_unhappy` | `min_i S_i(r)` | the least satisfied member is best served |

Questions and stopping use `G` only.

## Questions and stopping

For member `i` and question `q`, with the other members' beliefs fixed:

```text
gain(i, q) = sum_a P_i(a|q) max_r G_a(r)  -  max_r sum_a P_i(a|q) G_a(r)
```

Every member gets their highest-gain unasked question each round. When no single answer
can change the leading restaurant (all gains 0), the question that moves the leader's
margin most is asked. In the first round all members are alike, so they get the same question.

A group has 2 to 8 members. Another round is asked when the value of all members' answers
together exceeds `GroupConfig.question_cost` (.0005 log-satisfaction) per member asked. The
value enumerates every joint answer up to `6^5`; a larger round samples that many, with a
seed fixed per round. The first round is
always asked; `max_rounds` (4) caps the rest. A group whose menus come from one
restaurant gets it without a question. The cost comes from the dev check below; `max_rounds` is
an uncalibrated initial value.
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
  (at most 20 questions, as in the engine benchmark), then the picks over their beliefs.
- `separate_matched`: the same, capped at the group's number of rounds per member.
- `most_menus`: the restaurant with the most menus, without a question.

Every arm makes two picks the same way from `S_i` (`most_menus` from each restaurant's
share of the menus, so its picks are the two largest restaurants). The criteria judge the first pick;
`picks` reports each one's regret and mean and least satisfaction, and
`best_pick_regret_per_member` the regret if the group chose the truly better of the two.

Situations are `similar` (targets among each other's ten nearest menus), `conflict`
(far-apart targets) and `restricted` (one member has one of pork, wheat, milk or egg,
when a menu without it exists), each with groups of 2, 4, 6 and 8 (2, 3 and 5 in the
case sets before 2026-11-12). Results are per
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
5. The menus `group` tells members are, on mean, more similar to their targets than those
   `most_menus` tells them.

Criteria 1–3 were fixed before the first run; criterion 4 was added after it, before
the second case sets were frozen; criterion 5, before the third. `no_one_unhappy` and the
better of the two picks are reported, not judged.

```bash
python manage.py benchmark_group --date 2026-11-10 --dir DIR                   # freezes DIR/cases.json; commit it
python manage.py benchmark_group --date 2026-11-10 --dir DIR                   # ResponseOracle members, no key
python manage.py benchmark_group --date 2026-11-10 --dir DIR --simulator llm   # LLM members (paid)
python manage.py benchmark_group --source general --dir DIR2 ...               # the restaurants near the stations
```

The first run freezes `--groups` cases (default 6) per situation and size from the menus and `--seed`, and
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
satisfaction. Replayed on the cached LLM answers, a menu-count-normalized "specialty"
score chose specialties of the wrong dish (스키야키 for two 시샤모 lovers) and did worse in every situation.

### Fixed engine, two picks (2026-11-11, 11/10 lunch)

The engine with the fixes and two picks above, judged by criteria 1–5 on new case sets
of 6 and 12 groups per situation and size (`group-2026-11-10-{cafeteria,general}-g6`
and `-g12`; 18 and 36 groups per situation). LLM members used `openai:gpt-6-luna`, prompt
`45d1d4125724`; each answer cache started from the earlier 11/10 run's (and the 6-group
set's for the 12-group set), so 517, 607, 1,670 and 2,889 new calls were made.

| LLM members | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | --- | --- | --- | --- | --- | --- |
| 6 groups | pass | pass | pass | fails 2 | pass | pass |
| 12 groups | fails 2 | pass | pass | pass | fails 3 | fails 3 |

| LLM members, 12 groups, mean | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| questions: group / separate | 3.9 / 24.3 | 8.5 / 24.0 | 5.8 / 22.8 | 10.5 / 30.1 | 11.3 / 34.2 | 10.2 / 30.6 |
| regret per member: group | .037 | .013 | .021 | .042 | .045 | .037 |
| separate / matched / most menus | .008 / .055 / .072 | .015 / .033 / .022 | .013 / .024 / .197 | .024 / .058 / .078 | .031 / .045 / .069 | .020 / .035 / .063 |
| group − separate (95% interval) | +.030 ± .017 | −.003 ± .008 | +.008 ± .009 | +.018 ± .014 | +.014 ± .010 | +.017 ± .010 |
| group − matched (95% interval) | −.018 ± .018 | −.021 ± .010 | −.003 ± .009 | −.016 ± .014 | +.000 ± .007 | +.003 ± .008 |
| told-menu similarity: group / most menus | .840 / .814 | .817 / .781 | .833 / .770 | .894 / .845 | .823 / .790 | .888 / .859 |
| better of two picks: group | .012 | .008 | .009 | .034 | .035 | .025 |

Criteria 1, 4 and 5 pass everywhere. The verdicts of criteria 2 and 3 flip between the
two sizes; the 12-group intervals are the firmer evidence. Group mode asks about a third
of the questions of separate sessions and loses .01–.03 regret per member to them. With
the same number of questions it does better in the cafeteria's `similar` and `conflict`
groups, and no better in general `conflict` and `restricted` groups.
`no_one_unhappy` (reported only) did not raise the least satisfied member's similarity
in the 12-group general sets (.824 to .826 in `conflict`, .880 to .885 in `restricted`)
and lowered it in the cafeteria.

A replay of these 12-group cases afterwards, from the cached answers, found a bug: in 6 of
36 cafeteria `restricted` cases the allergic member could eat at only one restaurant, and
`no_one_unhappy` named another one where they had nothing (every other restaurant tied at
`min_i P_i = 0`, and name order won). Picks are now limited to restaurants with a menu for
every member. No `balanced` pick changes, so the verdicts above stand; those 6 cases now
get one pick.

### Expected satisfaction (dev check, already-judged 11/10 12-group cases, oracle members)

After the bug above, the restaurant score changed from `P_i` to `S_i` in every arm, for
questions, stopping and both picks. The old cost, .02 log-probability, stops after one round
in log-satisfaction units, so the cost was chosen on these already-judged cases (regret per
member, `group` / `separate` / `separate_matched`, and `group` questions):

| question cost | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | --- | --- | --- | --- | --- | --- |
| .002 | .038 / .014 / .057, 4.2 q | .020 / .018 / .022, 5.1 | .023 / .015 / .024, 4.1 | .058 / .025 / .059, 3.4 | .023 / .021 / .023, 3.6 | .023 / .011 / .027, 3.9 |
| **.0005** | .024 / .014 / .035, 7.1 | .016 / .018 / .022, 8.5 | .021 / .015 / .022, 6.0 | .055 / .025 / .056, 4.2 | .022 / .021 / .023, 5.6 | .023 / .011 / .022, 7.1 |
| .0002 | .021 / .014 / .028, 7.9 | .016 / .018 / .023, 10.0 | .016 / .015 / .017, 7.2 | .055 / .025 / .056, 4.3 | .024 / .021 / .024, 7.1 | .024 / .011 / .020, 7.8 |

With `P_i`, `group` regret in the general sets was .057 / .051 / .041. `S_i` halves it in
`conflict` and `restricted`; `separate` gains as much, since it aggregates the same way.
General `similar` groups stop after about four questions at any cost: one round's answers
rarely change the leading restaurant, so the myopic value of another round is small.
`no_one_unhappy` still does not raise the least satisfied member (general `conflict`
.857 for `balanced`, .831 for it).

