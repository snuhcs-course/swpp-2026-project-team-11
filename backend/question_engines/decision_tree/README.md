# P10: Adaptive cafeteria question engine

This package is a self-contained, no-key Python component for MVP1. It consumes
the existing `menus.services` candidate dictionaries and feature schema. It has
no Django, HTTP, Android, or Gemini dependency at runtime; Django is only used
by the demo commands and integration tests. NumPy supports bounded planning.

For review status and task owners, see the [P11 integration handoff](HANDOFF.md).

**Default:** `preference`, which selects questions by expected decision value
and proposes a concrete food when further questions do not justify their cost.
**Reference policies:** `greedy` information gain and `lookahead` intent search.

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
python -m pytest backend/menus backend/question_engines/decision_tree
```

## Integration example for P17/P19

```python
import datetime
from menus.services import get_catalog
from question_engines.decision_tree import DecisionTreeEngine

date = datetime.date(2026, 9, 29)
candidates, schema, version = get_catalog(date, meal="LU")
context = {"date": date.isoformat(), "meal": "LU", "feature_version": version}

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

`candidates` is the shape returned by `get_catalog`: positive integer
`food_id`, `name`, `display_name`, `food_group`, a complete `features` dictionary,
and `offers` containing cafeteria name, meal and price. Numeric food IDs remain
the identity boundary; display names are not unique. Feature values must be
finite scores in `[0,1]`. V2 also carries a complete `feature_std` dictionary.
Std must be finite, in `[0,0.5]`, and satisfy `std² <= mean * (1-mean)`.
An explicitly supplied partial/empty std map is rejected. V1 omits the map:
this retains legacy behavior, without asserting that its recipes have zero
variation. Candidate count and feature count are dynamic.

`schema` uses the existing `[{"key", "question"}, ...]` shape. English presentation
text is supplied for the legacy 23 keys and the v2 33 keys. V2 keeps grilled
and stir-fried, oily and greasy, large portion and filling, and the individual
seafood/cuisine features separate. A custom schema can provide
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
  and currently eligible member `food_ids`. Display the group heading for a group guess; the
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

V1 scores retain their original binary-yes interpretation. V2 means describe
feature intensity across ordinary recipes and serving styles; std describes
that recipe variation, not model confidence, a standard error, or user preference.
The two moments alone do not identify a distribution or a calibrated response
likelihood. Policy `decision-tree.2.0` therefore makes an explicit, provisional
response assumption for each food and feature:

```text
u = 4 * std²
response_score = (1 - u) * mean + u * 0.5
```

The factor 4 normalizes variance by the maximum possible variance on [0,1].
It reduces directional contrast toward a neutral response score as ordinary
recipes vary more. It never modifies the stored mean/std. Zero std (or missing
legacy std) reproduces the old channel; scores are not sharpened. Family intent
scores average these food-level response scores. Existing within-family
differences between food means still control the generic-intent resolution.
Recipe std does not itself raise the probability of `any` or `unknown`.

A normalized six-answer channel mixes positive and negative endpoint channels
using that response score, then applies session relevance and answerability.
The endpoint assumptions are `[.68, .24, .06, .02]` and their reverse.
These constants and the variance attenuation require human-response calibration.
No Beta, normal distribution, or truncated interval is inferred from mean/std.

Both greedy information gain and lookahead shortlists, rollouts, and posterior
updates use this channel. As a synthetic check, two equally likely foods with
means 0.8/0.2 produce about 78.3% posterior for the first after YES at std 0;
at std 0.35 for both, that posterior is about 64.4%. NO weakens symmetrically.
This is an algorithm check, not an observed recommendation-quality result.

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

`preference` separates the answer forecast from recommendation fit. Explicit
YES/PROBABLY YES/ANY/PROBABLY NO/NO/UNKNOWN have signed strengths
`[1, .5, 0, -.5, -1, 0]`. A food's utility is the sum of answered strengths
times its std-attenuated feature scores. Unasked traits contribute zero.
ANY and UNKNOWN both have zero directional utility, but keep their distinct
relevance/answerability updates in the forecast. Priors/posteriors break utility
ties only. Several foods can simultaneously have high fit.

For each unused question, let `S(f)` be current utility, `x(f,q)` the
std-attenuated score, and `w(a)` the answer strength. Enumerate all six outcomes:

```text
S_a(f) = S(f) + w(a) * x(f,q)
gain(q) = sum_a P(a|history,q) * max_f S_a(f)
          - max_f sum_a P(a|history,q) * S_a(f)
```

Both decisions include the expected contribution of the queried trait. This
prevents a question scoring well merely because all foods gain utility from it.
The maximum is over unrejected foods. The answer probabilities use the existing
full intent belief and std-aware channel; they are forecasts, not satisfaction
probabilities. This is a local, one-attribute EVSI approximation: the forecast
and explicit preference utility are not a fitted joint Bayesian user model.

Ask the highest-gain question when its gain exceeds
`EngineConfig.preference_question_cost` (initial experimental value `.06`,
in units of one fully satisfied feature). Before stopping, check the four best
root questions and all six outcomes for a useful second question. Add expected
positive child gain after its cost; ask only if the combined net value is
positive. This bounded two-step check uses exact outcome enumeration, no
particles or random rollouts. It is a local approximation, not global optimality.
The cost and answer strengths require user calibration; there is no default
question-count cap or 65% acceptance threshold for this policy.

Proposals and `recommend_now` rank by explicit preference utility, with forecast
weights breaking ties. This policy proposes concrete foods. The retained
intent policies can also propose groups. Rejection suppresses the proposed
aliases and updates the answer forecast; it does not invent dislikes for every
feature of the rejected food. Undo/snapshots replay both preference scores and
the forecast. `recommendation_scores` reports answered-preference fit on [0,1],
with .5 when there is no directional answer; it is not a distribution over foods
or a calibrated acceptance probability. Public REST step keys are unchanged.

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
features, std, offers, context, priors or engine/planner configuration. Policy
`decision-tree.1.0` and `decision-tree.2.0` snapshots are rejected after this semantic change. Persist the
exact candidate set and context used to start a session, or reload that same
immutable menu snapshot before restoring it.

## Evaluation and handoff

The committed September benchmark predates v2. The paired synthetic oracle still
uses a mean-based response model independent of engine beliefs, so it does not
establish that the new attenuation improves real user acceptance. V2 tests check
question ordering, both directions of posterior attenuation, channel normalization,
snapshot/undo behavior, dated schema selection, and unchanged API reply keys.

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
question-count benefit for lookahead and no first-guess advantage. These are
historical reference-policy results; they do not evaluate `preference`. Neither
this synthetic benchmark nor the DB's LLM annotations prove human satisfaction.
Latency here is Python computation on the development computer, not on-device
Android inference or a deployed-network guarantee.

The compact October 13 lunch regression fixture contains 146 reviewed mean/std
vectors. The reported user history reproduces 15 questions under `greedy`.
Replaying its first seven answers under `preference` proposes chicken soup
immediately. Letting the new policy choose its own order takes nine questions;
the newly asked spicy question is answered UNKNOWN in that test, not attributed
to the user. Separate deterministic noodle and burger profiles take six and
seven questions.

On the paired 24-target `ResponseOracle` simulated-user benchmark on the
October 13 v2 lunch fixture (146 candidates, 33 features, seed `20261006`),
comparing `preference`, `greedy`, and `lookahead`:

| Metric (October 13 v2, 24 trials) | Preference | Greedy | Lookahead |
| --- | ---: | ---: | ---: |
| Mean questions before first guess | 10.83 (median 10.0) | 28.12 (median 29.0) | 22.88 (median 26.5) |
| First-guess synthetic menu match | 7/24 (29.2%) | 7/24 (29.2%) | 6/24 (25.0%) |
| Mean total questions (until target matched) | 15.71 | 28.38 | 26.96 |
| Mean total interactions (questions + guesses) | 24.71 | 33.79 | 32.83 |

These are regression/synthetic checks, not human acceptance measurements or a
general question-count guarantee. The server policy can be switched without a
code change via `METCHU_DT_POLICY=preference|greedy|lookahead`
(`settings.RECOMMEND_DT_POLICY`).

Historical results on the September 29 v1 lunch fixture (193 candidates, 23 features,
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
