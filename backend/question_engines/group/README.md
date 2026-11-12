# Group mode (i4-P3)

A group rarely agrees on one dish, so group mode recommends **restaurants**, two of
different character, and each member's own menu at each. Every round, each member
answers a question chosen for them. The package is pure Python + NumPy on top of the
decision tree's intent model; the RL and LLM engines are not used. There is no REST
endpoint or client screen yet.

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
one a member wants counts for most of a match. A restaurant is an offer's `restaurant`
name, so `자하연식당>2층` and `>3층` are separate. Distance is not part of the score.
The first recommendation is `argmax G` and, for each member, the menu there closest in
expectation to the one they want (similarity averaged over `b_i`). The likeliest menu
would be arbitrary while `b_i` is still spread. The `fit` table of a catalog takes about
3 s for the 6,227 general menus and is cached per catalog and excluded menus.

A second restaurant follows, the best other one under its own score. Every pick is a
restaurant with a menu for every member; a kind with no such restaurant left is omitted,
and a group that no restaurant can serve is rejected:

| kind | score | meaning |
| --- | --- | --- |
| `balanced` | `sum_i log S_i(r)` | everyone is satisfied in balance |
| `no_one_unhappy` | `min_i S_i(r)` | the least satisfied member is best served |

Questions use `G` only.

## Questions and stopping

For member `i` and question `q`, with the other members' beliefs fixed:

```text
gain(i, q) = sum_a P_i(a|q) max_r G_a(r)  -  max_r sum_a P_i(a|q) G_a(r)
```

A group has 2 to 8 members. Every member gets their highest-gain unasked question each
round. When no single answer can change the leading restaurant (all gains 0), the member
gets the question their own preference session would ask (`PreferencePlanner`, as in a
single-user session), and none when that session would stop. In the first round all
members are alike, so they get the same question. The group stops after `max_rounds` (4)
or when no member has a question; a group whose menus come from one restaurant gets it
without a question. Results explain `max_rounds` and why a cost-based stop rule was dropped.
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
share of the menus, so its picks are the two largest restaurants). The criteria judge
the first pick; `picks` reports each one's regret and mean and least satisfaction, and
`best_pick_regret_per_member` the regret if the group chose the truly better of the two.

Situations are `similar` (targets among each other's ten nearest menus), `conflict`
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
menus and `--seed`, and stops. Later runs refuse menus that differ from the frozen ones.
The LLM members are the engine benchmark's simulated user (`METCHU_SIMULATOR_MODEL`),
told only the target's name; their answers are cached in `DIR/answers.jsonl`, shared by
the arms. Similarity and the answer model come from the same features, so absolute
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

### Current engine (2026-11-12)

Judged by criteria 1–5 on cases frozen before any run
(`group-2026-11-10-{cafeteria,general}-final/`, seed 20261115): 12 groups per situation
and size, so 48 groups per situation. The LLM run made 637 and 5,438 new calls (2.38M
input and 0.48M output tokens).

| Passed situations | cafeteria | general |
| --- | --- | --- |
| LLM members | none (all fail 1; `restricted` also fails 3) | `conflict`, `restricted` (`similar` fails 2) |
| oracle members | `similar`, `restricted` (`conflict` fails 4) | `similar` (`conflict`, `restricted` fail 3) |

| LLM members, mean | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| questions: group / separate | 20.0 / 36.0 | 20.0 / 36.4 | 19.1 / 33.9 | 20.0 / 49.4 | 20.0 / 51.6 | 20.0 / 47.9 |
| regret per member: group | .021 | .015 | .011 | .045 | .016 | .012 |
| separate / matched / most menus | .011 / .022 / .049 | .009 / .016 / .015 | .003 / .006 / .174 | .012 / .049 / .099 | .016 / .020 / .047 | .008 / .018 / .057 |
| group − separate (95%) | +.010 ± .011 | +.006 ± .005 | +.008 ± .005 | +.033 ± .012 | +.000 ± .004 | +.004 ± .005 |
| group − matched (95%) | −.001 ± .008 | −.001 ± .004 | +.005 ± .005 | −.003 ± .009 | −.004 ± .005 | −.005 ± .004 |
| told-menu similarity: group / most menus | .877 / .836 | .836 / .778 | .866 / .773 | .899 / .850 | .830 / .785 | .897 / .841 |

Asking every member until the round limit costs criterion 1 in the cafeteria: LLM
members end their own sessions after about 7 questions, so 4 rounds are 53–56% of them.
In general `similar` groups the group does as well as `separate_matched` with 4
questions each (.045 against .049), while separate sessions reach .012 with about 10.
The gap grows with the group (8 members: .066 against .006), since a member's answers
say nothing about the others' tastes in this model. `no_one_unhappy` does not raise the
least satisfied member (general `conflict` .834 for `balanced`, .817 for it).

How the questions were chosen was set on the already-judged 12-group cases (below) with
oracle members. The previous engine stopped when the value of another round fell below
a cost per question; general `similar` groups stopped after about four questions,
because one round's answers rarely change the leading restaurant. Looking two rounds
ahead did not change the stop, and asking the most informative question did not lower
regret. Asking each member whose answer cannot move the group their own question did:

| regret per member (questions) | cafeteria similar | conflict | restricted | general similar | conflict | restricted |
| --- | --- | --- | --- | --- | --- | --- |
| cost-based stop, .0005 | .024 (7.1) | .016 (8.5) | .021 (6.0) | .055 (4.2) | .022 (5.6) | .023 (7.1) |
| own question, 4 rounds | .021 (13.3) | .017 (13.3) | .019 (12.7) | .045 (13.3) | .022 (13.3) | .022 (13.3) |
| `separate` / `separate_matched` | .014 / .029 | .018 / .022 | .015 / .024 | .025 / .050 | .021 / .022 | .011 / .018 |

Six rounds lowered general `similar` to .040 but at 48% of the separate questions, and
`separate_matched` reached .034, so `max_rounds` stays 4.

### Earlier versions

Each version's cases, answers and reports are in `engine_benchmark_results/`; the
detailed tables are in this file's Git history.

| version (judged) | cases | LLM members failed | what the results showed, and the next change |
| --- | --- | --- | --- |
| best preference fit `U_i` (2026-11-10, 11/02 lunch) | `group-2026-11-02/`, 846 calls | every situation (criteria 2 and 3) | After one shared YES every member's fit was about .95 at many restaurants; the group stopped after one round and name order broke the tie. Scored beliefs instead. |
| probability `P_i(r)` that the wanted menu is served (2026-11-11) | `group-2026-11-10-{cafeteria,general}/`, 2,898 calls | general `similar` (2) | Members were told their likeliest menu (a 술국 lover got 한돈 족발한상); they are now told the closest. Twin menus could make two `similar` members want the same one. |
| `P_i`, two picks (2026-11-11) | `-g6/` and `-g12/` (18 and 36 groups), 5,683 calls | 12 groups: cafeteria `similar` (2), general `conflict` and `restricted` (3) | `no_one_unhappy` could name a restaurant with nothing for an allergic member; picks now need a menu for every member. `P_i` only counts menus and favored the largest restaurants; scored `S_i` instead. |
| `S_i`, cost-based stop .0005 (oracle only) | `-n2468/` | — | General `similar` failed criterion 2 (.061 against .032) after 5.5 questions. Changed to own questions until the round limit; the engine changed after these results, so the cases judge nothing further. |

Tried and dropped on already-seen cases: a prior uniform over restaurants instead of
menus (failed every check), a third pick by `sum_i P_i(r)` (never beat `balanced`), and a
menu-count-normalized "specialty" score (스키야키 for two 시샤모 lovers).
`no_one_unhappy` has not raised the least satisfied member in any judgement.
