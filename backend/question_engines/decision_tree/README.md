# P10: Adaptive cafeteria question engine

This package is a self-contained, no-key Python component for MVP1. It consumes
the existing `menus.services` candidate dictionaries and feature schema. It has
no Django, HTTP, Android, or Gemini dependency at runtime; Django is only used
by the demo commands and integration tests. NumPy supports bounded planning.

**Default:** greedy expected-information-gain selection with early menu guesses.
**Optional:** `lookahead`, ported from the personal prototype, which compares
questions and guesses under a bounded interaction-cost model.

## Quick start

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-09-29
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU
```

On Windows, activate with `.venv\Scripts\Activate.ps1` instead. The shared fixture
contains September 29 only: always pass the fixture date during development.
This dataset provides 193 lunch candidates with 23 features. A day without data
returns an explicit `unavailable` step. No API key or additional feature-extraction
call is needed.

Automated end-to-end smoke and optional planning:

```bash
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU --smoke
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU --policy lookahead --smoke
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU --output /tmp/session.json
python backend/manage.py test menus question_engines.decision_tree
```

## Integration example for P17/P19

```python
import datetime
from menus.services import get_candidates, get_feature_schema
from question_engines.decision_tree import DecisionTreeEngine

date = datetime.date(2026, 9, 29)
candidates = get_candidates(date, meal="LU")
schema = get_feature_schema()
context = {"date": date.isoformat(), "meal": "LU"}

engine = DecisionTreeEngine(candidates, schema, context=context)
step = engine.start()
# A request arriving while a question is displayed:
step = engine.answer(step["question_id"], "probably_yes")
# When a guess is displayed:
if step["type"] == "guess":
    step = engine.feedback(step["guess_id"], accepted=True)

diagnostics = engine.diagnostics()  # Engineering/experiment logs, not UI text.
snapshot = engine.snapshot()       # JSON-compatible persistent session record.
restored = DecisionTreeEngine.from_snapshot(candidates, schema, snapshot, context=context)
```

Each engine instance owns one session. P17 can wrap this concrete implementation
behind its shared `QuestionEngine` interface. P19 can serialize its step as the
HTTP response; P20 can record the separate diagnostics. HTTP session identity,
locking, revisions, idempotency keys and storage belong to that wrapper. The
engine is not intended to be mutated concurrently by multiple requests.

### Inputs

`candidates` is the exact shape returned by `get_candidates`: positive integer
`food_id`, `name`, `display_name`, `food_group`, a complete `features` dictionary,
and `offers` containing cafeteria name, meal and price. Numeric food IDs remain
the identity boundary; display names are not unique. Feature values must be
finite probabilities in `[0,1]`. Candidate count and feature count are dynamic.

`schema` uses the existing `[{"key", "question"}, ...]` shape. English presentation
text is supplied for the current 23 keys. A custom schema can provide
`question_en` and `family`. Families share session-level importance estimates.
The original schema, candidate values/offers, context and prior all contribute
to the replay fingerprint. Source food and cafeteria names retain their original
language; all authored prompts, answer labels, errors and documentation are English.

Optional `priors={food_id: weight, ...}` must cover all candidates with finite,
positive weights; the engine normalizes them. Default food priors are uniform.
The old prototype's hand-scored 500-food popularity list is not imported into
the team dataset. Filter verified eligibility restrictions before constructing
the engine; sensory features alone do not establish ingredient safety.

### Methods and output contract

| Method | Effect |
| --- | --- |
| `start()` / `next_step()` | Return the cached current step; repeated reads do not apply an answer twice |
| `answer(question_id, answer_id)` | Validate the current question, update belief and select the next step |
| `feedback(guess_id, accepted)` | Accept the offered menu, or softly update belief and suppress its visible aliases |
| `recommend_now()` | Offer a concrete, eligible input food immediately |
| `undo()` | Restore the exact step before the last event |
| `snapshot()` / `from_snapshot(...)` | Persist/replay displayed actions without rerunning timed search |
| `diagnostics()` | Separate model, question-count, posterior and planning logs |

All methods return detached JSON-compatible dictionaries. Invalid or stale IDs
raise `ValueError` before applying an answer or feedback. There is no default
question-count limit. `EngineConfig(max_questions=N)` is an explicit experiment
cap. Each available question is used at most once.

Question example:

```json
{
  "type": "question",
  "question_count": 0,
  "question_id": "q:soupy",
  "text": "Do you feel like something with broth?",
  "options": [
    {"id": "yes", "label": "Yes, sounds good"},
    {"id": "probably_yes", "label": "Probably yes"},
    {"id": "any", "label": "Doesn't matter"},
    {"id": "probably_no", "label": "Probably not"},
    {"id": "no", "label": "No"},
    {"id": "unknown", "label": "Not sure"}
  ]
}
```

Other step types:

- `guess`: `guess_id`, `target_kind` (`food` or `group`), `food` (a representative
  real candidate), and optionally `group` with `group_id`, source display name
  and member `food_ids`. Display the group heading for a group guess; the
  representative is one available concrete option, not a claim that its variant
  has already been identified.
- `recommendation`: the accepted concrete `food` and original offers. Accepting
  a group ends with the representative that was displayed, without another
  forced variant question. Its real `food_id` remains in the input candidates.
- `unavailable`: a reason (`empty_candidates` or `candidates_exhausted`) and
  English product text. No food ID is fabricated when candidates are absent.

`question_count` counts answered questions in the active history. Repeated reads
do not increment it; undo restores it. For actual user effort, P20 should log
the displayed steps and undo requests as well as this counter.

## Inference and hierarchy

Each food occurs once under its `food_group`; groups with at least two foods
receive internal parent nodes. This is a shallow classification hierarchy from
the current meal candidates, not a verified culinary ontology. Free-form group
quality depends on the DB annotations. Internal group IDs are never presented
as real database food IDs.

The latent state distinguishes a specific food from indifference within a
menu group. 35% of a grouped food's prior is allocated to its generic group
intent; the rest stays specific. Marginalizing back to foods reproduces the
original normalized prior, so adding a parent does not duplicate probability.

The team's feature `p` is used directly as a binary-yes propensity. A normalized
six-answer observation channel extends that binary input: informative answer
probabilities are linear mixtures of the positive/negative endpoint channels,
multiplied by session relevance and answerability. It does **not** temperature-
sharpen an already supplied probability. The endpoint assumptions are
`[.68, .24, .06, .02]` for positive intent and their reverse for negative intent.
These are not measured user-response probabilities.

`any` lowers importance in the related family and can favor a generic intent
when variants differ on that attribute. `unknown` preserves food direction and
lowers expected answerability. Group-level importance and resolution use a
factorized approximation, not an exact joint posterior over every preference.

Guess-acceptance assumptions are `.97` for matching intent, `.72` for a broader
proposal, `.88` for a specific member of a generic intent, and `.005` for
disjoint menus. Rejection updates with `1 - acceptance` while keeping belief
positive. Rejected display-name aliases and group descendants are suppressed
from later proposals; a group whose members are all suppressed cannot be offered.

## Policies and computation

`greedy` selects the unused question with highest expected information gain over
the current intent belief and six response outcomes. It guesses when predicted
acceptance reaches `.65`, useful information falls below `.001` bits, or the
finite question bank ends. These reference settings are configurable and need
user calibration.

`lookahead` compares question cost with proposal cost and rejection continuation:

```text
Q(question) = 1 + expected continuation cost after an answer
Q(guess) = 1 + P(reject) * (3 + continuation cost + first-miss penalty)
```

The first miss adds 12 cost units. Defaults preserve the prototype's bounded
search: maximum optimized depth 2, root question beam 4, next-level beam 1,
96 planning particles, 8 rollouts of at most 16 further interactions, 640 nodes,
and a 180ms soft deadline. The full inference posterior is never pruned.
Information gain only screens the question shortlist. A complete comparison
at one depth is retained if a deeper level cannot finish. The timing budget
does not count Python imports or model construction, which the benchmark
includes separately on the first decision.

Rollouts use a cheap continuation policy and a finite guess-only tail when they
end. A paired-error guard avoids promoting unstable guess advantages. Sampled
branches, limited action candidates, the importance factorization and assumed
response model mean this is an approximate policy; it is not globally optimal
or a statistically guaranteed first-pick acceptance rate.

Snapshots store actual presented steps because time-limited searches can finish
at different depths on different machines. Restore rejects changes in schema,
features, offers, context, priors or engine/planner configuration. Persist the
exact candidate set and context used to start a session, or reload that same
immutable menu snapshot before restoring it.

## Evaluation and handoff

```bash
python backend/manage.py benchmark_decision_tree --date 2026-09-29 --meal LU --trials 24 --output /tmp/engine-benchmark.json
```

Both policies use the same fixed targets and order-independent answer oracle.
Oracle importance is independent of engine state. Group membership or an
identical visible dish name counts as a **synthetic menu match**; exact food-ID
matching and group size are reported separately. This avoids falsely counting
a broad group as an exact dish identification. P20 should also distinguish
these levels when comparing MVP1 with an LLM that returns concrete foods.

The checked-in [24-target report](benchmarks/cafeteria_20260929_lunch.json) records
the dataset fingerprint, policy configuration, environment, per-trial answers,
guesses, all interaction counts and latency. The small run shows only a minor
question-count benefit for lookahead and no first-guess advantage. Therefore
greedy is the default; lookahead remains an explicit experiment option. Neither
this synthetic benchmark nor the DB's LLM annotations prove human satisfaction.
Latency here is Python computation on the development computer, not on-device
Android inference or a deployed-network guarantee.

Recorded results on the September 29 lunch fixture (193 candidates, 23 features,
seed `20261006`, 24 paired synthetic targets):

| Metric | Greedy | Lookahead |
| --- | ---: | ---: |
| Mean answered questions | 20.88 | 20.21 |
| Mean questions plus guesses | 22.88 | 22.21 |
| First-guess synthetic menu match | 11/24 | 11/24 |
| Exact representative food-ID match | 9/24 | 10/24 |
| Decision p95 on the development computer | 1.94ms | 138.75ms |
| Maximum recorded decision latency | 66.64ms | 184.28ms |

The initial decision includes model construction; later timings include answer
or rejection processing and next-step selection. These timings fall below
500ms in this run. The sample is small, and neither policy demonstrates a
real-user first-pick acceptance target from this experiment.

P17 can now wrap the documented engine API. P19 can render the four step types
and forward the stable six answer IDs. P20 can reuse the deterministic oracle
for policy comparisons and log `diagnostics()` alongside actual user acceptance.
The LLM engine, shared REST layer and Android screens remain separate assigned
components.

## AI-assisted development

This contribution adapts the author's earlier Codex-assisted prototype to the
team's existing DB contract. The adaptation removes its fixed catalog and score
sharpening, retains bounded planning/replay tests, adds English presentation,
and validates the actual fixture. Human teammate review is still required.
Tests include independent small-state cost enumeration, invalid/stale inputs,
importance updates, group rejection, snapshot/undo without search, no-key real
data integration, and identical-oracle evaluation. No human-hour or token-usage
figures are inferred from automated test duration.
