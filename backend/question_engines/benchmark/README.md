# Question engine benchmark: decision tree (MVP1) vs LLM engine (MVP2)

Which question engine should the app ship? Both engines play the same scenarios
against a simulated user, and people play some sessions by hand (the user study)
to check the simulation. Benchmarks are experiments that inform this choice; the
pytest tests check that the benchmark code works.

**Main metrics, per situation and engine:** questions per session, first-pick
acceptance rate, latency per session and cost per session. The goal is a first pick
of at least 50%, and 15% above the baselines. Every figure is per situation: the
situations measure different things, so a mean over them means nothing.

## Running it

One command runs everything and keeps it in `engine_benchmark_results/NAME/`
(committed, so the team shares it). Running the same name again continues a
stopped run without repeating finished sessions:

```bash
cd backend
export METCHU_MAX_QUESTIONS=20                  # the question limit both engines get (the server's setting)
export METCHU_SIMULATOR_MODEL=openai:gpt-6-luna  # the simulated user of the 2026-10-20 runs (OPENAI_API_KEY)
python manage.py run_engine_benchmark --name 2026-10-20 --date 2026-10-20 --dry-run   # LLM calls only
python manage.py run_engine_benchmark --name 2026-10-20 --date 2026-10-20 --limit 2 --repeats 1  # small first
python manage.py run_engine_benchmark --name 2026-10-20 --date 2026-10-20
```

`config.json` records the question limit, the models, the prompts and the scenarios actually
played. A session that ended in an error (a lost connection) is played again by the next run of
the same name; three such sessions in a row stop the run.

```
NAME/
  config.json              menus, counts, repeats, models, the LLM engine's and the simulated
                           user's prompts (text and id), DT policy, git commit
  scenarios.json           made once; delete it to make new scenarios
  sessions/                sessions.jsonl, simulator_cache.jsonl (readable), run.log
  report.md, summary.json  the sections below
  sessions.csv, questions.csv, proposals.csv   one row per session, question, proposal
  1_main_metrics/ 2_baselines/ 3_situations/ 4_paired_tests/ 5_latency_and_cost/
  6_stability/ 7_recommend_now/ 8_similarity/ 9_user_study/
  9_user_study/human/      people's sessions, read when the report is written
```

The user study, 30+ students with two sessions on each engine:

```bash
R=../engine_benchmark_results/2026-10-20
python manage.py play_engine_session --scenarios $R/scenarios.json --output $R/9_user_study/human/kim.jsonl --tester kim
# four times per tester; then
python manage.py validate_simulator --human $R/9_user_study/human/*.jsonl --output $R/9_user_study/simulator_check.jsonl
python manage.py run_engine_benchmark --name 2026-10-20   # rewrites the report with them
```

The steps can also be run one by one: `build_engine_scenarios`, `collect_engine_sessions`
(the only step with LLM calls besides the user study), `benchmark_engines` (no LLM call).

## Scenarios (`scenarios.py`)

100 users by default (`--counts`):

| Situation | Count | What the user wants | A proposal is accepted when |
|---|---|---|---|
| `in_menu` | 40 | one menu served that day | it is the wanted menu or a kind of it, or the simulated user would take it |
| `multiple` | 20 | 2-3 served menus with nothing in common | it is one of them or a kind of one, or the simulated user would take it |
| `not_in_menu` | 20 | a tagged dish of another day that nothing satisfies | the simulated user would take it |
| `close_alternative` | 20 | a served menu next to a dish whose features differ by at most 0.05 on average (the feature benchmark's collision) | it is the wanted menu or a kind of it; never the close alternative |

"A kind of it": wanting 볶음밥, 소고기볶음밥 is fine; wanting 닭고기볶음밥, it is not. A
decision-tree group proposal is accepted only when every menu in it is fine.
Kinds are found by name containment, ignoring spacing and size markers. The rule
alone is too strict for people (wanting 햄버거, a person takes 치즈버거), so when it says
no, the simulated user is asked whether they would take the proposal anyway: only
if it is essentially the same dish, not any decent meal. When the wanted menu is not
served, the question is whether the proposal would do instead (same craving: a pork
cutlet for a fish cutlet, not jjajangmyeon). A dish's set and single version get one
verdict. The report also keeps the strict view, "first pick (exact)": the rule alone
(not defined when the wanted menu is not served).

Each scenario has a **certainty** level, taken in turn: the share of answers that
are blurred after the simulated user gives them, the same way for both engines.
High 0%, medium 15%, low 30%; half become "Not sure"/"Doesn't matter", half are
turned around. Both engines get the same menus, the same users and the same answers.

Each menu is loaded as the app loads it (`get_catalog`) and copied into
`scenarios.json`, so a later menu fetch cannot change a scenario. All menus must
have the same feature version (today only fully v2-tagged days qualify).

## The engines and the simulated user (`harness.py`, `simulator.py`)

The engines are built as the server builds them: `RECOMMEND_MAX_QUESTIONS`, the
decision tree's `RECOMMEND_DT_POLICY`, and the LLM engine on OpenRouter
(`OPENROUTER_API_KEY`, `METCHU_LLM_MODEL`). Both engines get everything else the same
way, so the comparison is fair: the same scenarios, the same simulated user with the
same prompts asked one question at a time, the same blurring, the same verdict rule,
and the same number of repeats per scenario (`--repeats`, default 3). The decision tree
is deterministic, but the blurred answers change with the repeat. In the first full
run, 3 instead of 5 LLM repeats would have widened the first pick's standard error by
only 5% (most of it comes from sampling 100 scenarios).

The simulated user is an LLM that knows only the wanted menu's name, never its
features, so the decision tree is also tested against wrongly extracted features.
It is `METCHU_SIMULATOR_MODEL` (`<provider>:<model>` as in `menus/llm.py`, default
`google:gemini-3.5-flash`), a different model from the LLM engine's, since the same
model would understand its own questions too well. A user happy with several menus
answers yes when a question is true of at least one of them, no when of none ("any"
only when it does not matter for any). A question naming a kind of dish asks for that
dish: wanting a chicken burger, "fried chicken?" is no and "chicken?" yes. Answers
are cached, so reruns and repeats ask nothing twice, and the same question gets the
same answer from either engine. Its calls and tokens are recorded per session
(benchmark overhead, section 5); OpenAI and Google report no price, so cost them
with the provider's price list.

## What is recorded (`harness.py`, `metrics.py`, `cost.py`)

Per session (`sessions/sessions.jsonl`): outcome (accepted, gave up after 5 rejected
proposals, unavailable, error), whether the first proposal was accepted and whether it
was a wanted menu by the rule, the final menu, engine time per step (the user's time
is never counted), and a trace with enough to tell later what went wrong:

- each question: the text, the answer the engine got, the simulated user's raw answer
  and whether it was blurred (a wrong answer from the LLM, or on purpose);
- each proposal: the dish or group, the verdict and how it was reached (`judged_by`:
  `rule`, `simulator`, `rule_only` next to a close alternative, `person`);
- at each decision-tree step: its top 5 candidates with probabilities, the entropy,
  and why it asked or proposed;
- for the LLM engine: every call (latency, attempts, fallback reason, tokens, cost).
  Why an attempt was retried (a repeated question, an invalid reply) is in `run.log`.

At 0, 2 and 4 questions a copy of the session is asked to "recommend now"; its LLM use
is counted apart. The copy at 0 questions is the no-question baseline. The simulated
user's cache says, for each answer, who was asked what under which prompt.

Similarity is 1 - mean feature difference to the closest wanted menu, recorded in
every situation, with the best any candidate reached (regret) and the final menu's
rank among the candidates.

## The report (`report.py`)

Every table has one row per situation and engine.

| # | Section | What it shows |
|---|---|---|
| 1 | Main metrics | questions / session, questions to accept, first pick (and exact), latency p50/p95, cost / session; also LLM sessions with and without a fallback |
| 2 | Baselines | first pick (exact) against proposing without a question, a random dish and the other engine, as points and as a ratio, with a 95% interval; served situations only |
| 3 | Situations | success, first pick, interactions, giving up, similarity, regret, rank by situation and certainty |
| 4 | Paired tests | LLM - decision tree per scenario: bootstrap interval, Wilcoxon, McNemar |
| 5 | Latency and cost | session and step latency, LLM calls, tokens, cost (mean, p95), fallback and error rates, recommend-now overhead, the simulated user's calls and tokens |
| 6 | Stability | each engine over repeats: same final menu, same outcome, questions SD |
| 7 | Recommend now | success and similarity after k questions |
| 8 | Similarity | similarity of accepted and rejected proposals, for the not-served threshold |
| 9 | User study | people's sessions, satisfaction (1-5), the simulated user's agreement with people on answers and on verdicts |

## Cost

Every session costs one simulated-user call per new question and per proposal the
name rule does not accept; the decision tree's repeats ask its fixed questions again
from the cache. An LLM engine session also costs one engine call per question or
proposal (and retries), and three for the "recommend now" copies. In the first full
run (2026-10-20, 20-question limit, the earlier simulated-user prompts) an LLM engine
session averaged 9.8 questions, 4.1 proposals, 14.6 engine decisions (2,540 input tokens
each) and $0.018 on OpenRouter. `--dry-run` prints an estimate, and `--limit` and
`--repeats` start small.

## Results

### 2026-10-20

100 scenarios on the 2026-10-20 lunch menu (104 dishes), both engines 3 times each (600
sessions), 20-question limit, decision tree `preference`, LLM engine
`google/gemini-3.5-flash-lite`, simulated user `openai:gpt-6-luna`. Full report:
`engine_benchmark_results/2026-10-20/report.md`; a one-page summary with plots:
`engine_benchmark_results/2026-10-20/benchmark_report.md`.

| Situation | First pick (exact), DT / LLM | Success, DT / LLM | Questions, DT / LLM | Latency p50, DT / LLM | LLM cost / session |
|---|---|---|---|---|---|
| `in_menu` | 40.0% (32.5%) / 26.7% (20.8%) | 64.2% / 43.3% | 10.2 / 8.2 | 36 ms / 16.2 s | $0.0127 |
| `multiple` | 31.7% (6.7%) / 38.3% (21.7%) | 30.0% / 38.3% | 9.2 / 7.9 | 46 ms / 15.0 s | $0.0121 |
| `not_in_menu` | 5.0% / 8.3% | - | 14.8 / 8.9 | 61 ms / 18.8 s | $0.0149 |
| `close_alternative` | 26.7% / 15.0% | 63.3% / 46.7% | 10.4 / 7.8 | 42 ms / 15.9 s | $0.0124 |

Success: the final menu is a wanted menu by the name rule (not defined when it is not
served). The decision tree costs nothing.

Findings:

- Neither engine reaches the 50% first-pick goal in any situation.
- `in_menu`: the decision tree is better. First pick (exact) clears the no-question
  baseline by 32.5 points (LLM engine: 20.0), and it ends on the wanted menu more often
  (LLM - DT: -20.8 points [-32.5, -10.0]).
- `multiple`: the LLM engine is better (first pick exact 21.7% vs 6.7%), but no
  difference is significant with 20 scenarios. The decision tree's exact first pick is
  below its own no-question baseline.
- `not_in_menu`: both engines rarely find a substitute the simulated user takes (5% and
  8%); 83-88% of these sessions end with the user giving up. The decision tree asks 5.9
  more questions here.
- `close_alternative`: the decision tree's first pick is 11.7 points higher, not
  significant (LLM - DT: [-31.7, +6.7]).
- The LLM engine asks 1.3-5.9 fewer questions in every situation (all significant), takes
  15-19 s per session against 36-61 ms, and is less stable over repeats (same final menu
  45-90% against 58-93%). 2 of 300 LLM sessions used a fallback.
