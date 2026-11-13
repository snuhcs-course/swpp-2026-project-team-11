# Group mode (i4-P3)

A group rarely agrees on one dish, so group mode recommends **restaurants**, two of
different character, and each member's own menu at each. Every round, all members
answer the same question. The package is pure Python + NumPy on top of the
decision tree's intent model; the RL and LLM engines are not used. There is no REST
endpoint or client screen yet.

## Model

Each member keeps their own decision-tree intent belief `b_i(f)`, the probability that
menu `f` is the one they feel like (uniform over menus before any answer; the same
answer model as the single-user engine). A member excludes the offers they cannot eat,
each a menu at one restaurant: equivalent menus share a food ID, and one restaurant's
may hold an allergen another's does not. A menu they can eat nowhere has belief 0 for
that member only.

```text
fit_i(r, f) = similarity of f to the closest menu at r that i can eat   # 0 if there is none
S_i(r)      = sum_f b_i(f) fit_i(r, f)                                  # i's expected satisfaction at r
G(r)        = sum_i log S_i(r)                                          # Nash welfare
```

Similarity is 1 - mean absolute feature difference, as in the benchmark: a menu like the
one a member wants counts for most of a match. A restaurant is a place, an offer's
`restaurant` name with its coordinates: branches of one chain are separate, and so are
`자하연식당>2층` and `>3층`. Distance is not part of the score.
The first recommendation is `argmax G` and, for each member, the menu there closest in
expectation to the one they want (similarity averaged over `b_i`). The likeliest menu
would be arbitrary while `b_i` is still spread. The `fit` table over every served menu
takes about 3 s for the 6,227 general menus; it is built once per catalog and shared
read-only, and a member's exclusions recompute only the rows of the restaurants they change.

A second restaurant follows, the best other one under its own score. Every pick is a
restaurant with a menu for every member; a kind with no such restaurant left is omitted,
and a group that no restaurant can serve is rejected:

| kind | score | meaning |
| --- | --- | --- |
| `balanced` | `sum_i log S_i(r)` | everyone is satisfied in balance |
| `no_one_unhappy` | `min_i S_i(r)` | the least satisfied member is best served |

Questions use `G` only.

## Questions and stopping

A group has 2 to 8 members, and every round all of them answer the same unasked
question. For member `i` and question `q`, with the other members' beliefs fixed:

```text
gain(i, q) = sum_a P_i(a|q) max_r G_a(r)  -  max_r sum_a P_i(a|q) G_a(r)
```

The round's question has the largest `sum_i gain(i, q)`, an approximation of the value
of everyone's answers together, whose 6^n combinations are too many to sum. When no
single answer can change the leading restaurant (all gains 0), the question tells the
members most about their own tastes: the largest sum of each member's expected
information about their intent (mutual information between answer and `b_i`). The group
stops after `max_rounds` (4), or when no member's own preference session
(`PreferencePlanner`, as in a single-user session) would ask another question while no
answer can change the leading restaurant; a group whose menus come from one restaurant
gets it without a question. Results explain these choices. Sums over a restaurant's
menus are one matrix product, so a round over the 6,227 general menus and 586
restaurants of a lunch takes about a second per member.

```python
from question_engines.group import GroupEngine

engine = GroupEngine(candidates, schema, excluded=[set(), {(food_id, ("식당", 37.48, 126.95))}])
while not engine.finished:
    for member, step in engine.questions().items():   # the round's question, per member who has not answered
        engine.answer(member, step["question_id"], answer_id)
result = engine.recommendation()   # {"picks": [{"kind", "restaurant", "lat", "lng", "menus": [food or None per member]}], "rounds"}
```

## Benchmark

`benchmark_group` compares four arms on the same simulated members, each wanting one
target menu. A member's true satisfaction with a restaurant is the best feature
similarity to that target among the offers there they can eat; the true group score is
`sum_i log(.05 + satisfaction_i)`.

- `group`: this engine.
- `separate`: each member's own `preference` session until it would propose a menu
  (at most 20 questions, as in the engine benchmark), then the picks over their beliefs.
- `separate_matched`: the same, capped at the group's number of rounds per member.
- `most_menus`: the restaurant with the most menus, without a question.

Every arm makes two picks the same way from `S_i` (`most_menus` from each restaurant's
share of the menus, so its picks are the two largest restaurants). The criteria judge
the first pick; `picks` reports each one's regret and mean and least satisfaction, and
`best_pick_regret_per_member` the regret if the group chose the truly better of the two.

Situations are `similar` (targets among the first member's ten nearest menus), `conflict`
(far-apart targets) and `restricted` (one member has one of pork, wheat, milk or egg,
when a menu without it exists), each with groups of 2, 4, 6 and 8 (2, 3 and 5 in the
case sets before 2026-11-12). Results are per situation, never averaged across them:
the share of groups given the truly best restaurant, Nash regret per member, the least
satisfied member, the mean similarity of the menus members are told (each arm picks them
as the engine does), total questions and rounds.

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

The first run freezes `--groups` cases (default 6) per situation and size from the
menus and `--seed`, and stops. Later runs refuse menus or allergy restrictions that
differ from the frozen ones. An allergic member can eat an offer when the catalog
without that allergen keeps it. That catalog merges equivalent menus again, under other
food IDs, so its offers are matched to the full catalog's by menu title, features and
offer; the command stops if one does not match exactly one.
The LLM members are the engine benchmark's simulated user (`METCHU_SIMULATOR_MODEL`),
told only the target's name; their answers are cached in `DIR/answers.jsonl`, shared by
the arms, and each question is asked once even when cases run in parallel. `most_menus`
picks only restaurants where every member can eat, like the other arms. An allergic
member's own sessions see the menus they can eat somewhere, under the group's food IDs.
Similarity and the answer model come from the same features, so absolute
satisfaction is optimistic; the comparison between arms is what the criteria judge.
Taking the best menu of a restaurant also favors restaurants with many menus, which
`most_menus` makes visible.

## Results

Since 2026-11-11 the menus are the 11/10 lunch from a copy of the live server's food DB
taken 2026-11-10 23:27 (release `local-hours-fab28cd3fe36`; kept outside Git): 244
cafeteria menus at 22 restaurants and 6,227 general menus at 584 restaurants. The live
release also filters general menus by opening hours (4,227 at lunch); `main` does not
yet. LLM members used `openai:gpt-6-luna`, prompt `45d1d4125724`, in every run. Later
answer caches started from earlier runs', so only new questions were paid for.

### Current engine: one shared question (2026-11-12)

Judged by criteria 1–5 on cases frozen before any run
(`group-2026-11-10-{cafeteria,general}-shared/`, seed 20261116): 12 groups per situation
and size, so 48 groups per situation. The LLM run made 619 and 5,153 new calls. The
general run stopped once on an OpenAI connection error and resumed from its cache, so
`llm.json` counts only the 4,215 calls after it; the recorded tokens are 0.24M input and
0.05M output (cafeteria) and 1.65M and 0.33M (general, without the first 938 calls).

The PR review then found two benchmark faults. `most_menus` could pick a restaurant with
nothing for the allergic member (12 of 48 cafeteria `restricted` groups; its regret there
was .185), and parallel cases could ask the same question twice (17 cafeteria and 5
general questions; 3 and 1 got different answers, so arms could see different answers).
Both are fixed. The cafeteria reports were replayed from the cached answers with no new
call, so their `llm.json` shows 0 calls (the paid run's usage is in commit 2ddb37d); two
`similar` groups changed and no verdict did. The general reports had no such pick and
were not replayed.

A second review found three more. Allergy eligibility was kept per menu, so an
equivalent menu safe at one restaurant counted as safe at every restaurant serving it;
branches with one name were one restaurant serving the union of their menus; and an
allergic member's own sessions dropped the menus merged under another food ID. All are
fixed, and the cases now record the allergy restrictions (added from the same DB copy).
The cafeteria has none of these, and its reports replayed unchanged with no new call.
The general reports were replayed too, which also gives every arm one answer per
question: the oracle report changed in 5 groups (1 `similar`, 4 `restricted`), and the
LLM report, after 8 new questions (3,103 input and 370 output tokens), in 2 (1 `similar`,
1 `restricted`). No verdict and no mean in the table below changed.

| Passed situations | cafeteria | general |
| --- | --- | --- |
| LLM members | none (all fail 1; `similar` also fails 3) | `conflict`, `restricted` (`similar` fails 2) |
| oracle members | `similar`, `conflict` (`restricted` fails 3) | all three |

| LLM members, mean | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| questions: group / separate | 20.0 / 36.9 | 20.0 / 35.8 | 20.0 / 34.3 | 20.0 / 48.0 | 20.0 / 50.9 | 20.0 / 49.6 |
| regret per member: group | .013 | .011 | .009 | .033 | .018 | .014 |
| separate / matched / most menus | .007 / .009 / .046 | .007 / .011 / .012 | .003 / .014 / .011 | .009 / .034 / .086 | .017 / .020 / .061 | .011 / .014 / .051 |
| group − separate (95%) | +.006 ± .006 | +.004 ± .007 | +.006 ± .006 | +.024 ± .009 | +.001 ± .005 | +.003 ± .004 |
| group − matched (95%) | +.004 ± .006 | −.001 ± .007 | −.005 ± .007 | −.001 ± .008 | −.001 ± .003 | −.000 ± .003 |
| told-menu similarity: group / most menus | .887 / .819 | .831 / .777 | .863 / .835 | .909 / .846 | .825 / .789 | .892 / .845 |

The cafeteria fails criterion 1 as before: LLM members end their own sessions after
about 7 questions, so 4 rounds are 54–58% of them. General `similar` groups still lose
to separate sessions, and more so in larger groups (8 members: .040 against .001), since
a member's answers say nothing about the others' tastes. With the same number of
questions the group is no better than `separate_matched` (−.005 to +.004). `no_one_unhappy`
does not raise the least satisfied member (general `conflict` .842 for `balanced`, .828
for it).

The shared question was chosen on the previous engine's already-judged cases
(`-final/`) with oracle members (regret per member):

| | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| own question per member (previous engine) | .029 | .017 | .008 | .058 | .019 | .020 |
| shared: sampled joint answers | .029 | .023 | .009 | .057 | .019 | .020 |
| shared: `sum_i gain`, most information when 0 | .027 | .018 | .009 | .055 | .018 | .017 |
| shared: `sum_i gain`, then the members' own decision value | .031 | .021 | .010 | .061 | .019 | .017 |
| shared: `sum_i gain`, then the most common own question | .031 | .021 | .009 | .061 | .019 | .017 |
| `separate` / `separate_matched` | .024 / .034 | .013 / .021 | .007 / .013 | .046 / .063 | .017 / .018 | .017 / .018 |

Sampling 256 joint answers almost never gives a value of exactly 0, so it never fell back
and kept asking about restaurants. Every variant asked 4 rounds. `max_rounds` was set on
the per-member engine below: six rounds lowered general `similar` to .040 but at 48% of
the separate questions, while `separate_matched` reached .034.

### Earlier versions

Each version's cases, answers and reports are in `engine_benchmark_results/`; the
detailed tables are in this file's Git history. They have the faults fixed above:
`most_menus` in `restricted` groups, allergies per menu and restaurants per name.

| version (judged) | cases | LLM members failed | what the results showed, and the next change |
| --- | --- | --- | --- |
| best preference fit `U_i` (2026-11-10, 11/02 lunch) | `group-2026-11-02/`, 846 calls | every situation (criteria 2 and 3) | After one shared YES every member's fit was about .95 at many restaurants; the group stopped after one round and name order broke the tie. Scored beliefs instead. |
| probability `P_i(r)` that the wanted menu is served (2026-11-11) | `group-2026-11-10-{cafeteria,general}/`, 2,898 calls | general `similar` (2) | Members were told their likeliest menu (a 술국 lover got 한돈 족발한상); they are now told the closest. Twin menus could make two `similar` members want the same one. |
| `P_i`, two picks (2026-11-11) | `-g6/` and `-g12/` (18 and 36 groups), 5,683 calls | 12 groups: cafeteria `similar` (2), general `conflict` and `restricted` (3) | `no_one_unhappy` could name a restaurant with nothing for an allergic member; picks now need a menu for every member. `P_i` only counts menus and favored the largest restaurants; scored `S_i` instead. |
| `S_i`, cost-based stop .0005 (oracle only) | `-n2468/` | — | General `similar` failed criterion 2 (.061 against .032) after 5.5 questions. Changed to own questions until the round limit; the engine changed after these results, so the cases judge nothing further. |
| own question per member, 4 rounds (2026-11-12) | `-final/`, 6,075 calls | cafeteria all (1; `restricted` also 3), general `similar` (2) | When no answer could move the group, a member got their own session's question; this replaced the cost-based stop, which stopped general `similar` groups after about four questions (oracle regret .055 → .045 on the `-g12/` cases). Then replaced by one shared question per round. |

Tried and dropped on already-seen cases: a prior uniform over restaurants instead of
menus (failed every check), a third pick by `sum_i P_i(r)` (never beat `balanced`), and a
menu-count-normalized "specialty" score (스키야키 for two 시샤모 lovers).
`no_one_unhappy` has not raised the least satisfied member in any judgement.
