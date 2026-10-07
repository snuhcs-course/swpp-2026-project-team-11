# P13/P14: LLM question engine (MVP2)

The LLM receives **only the day's food names**, never the extracted features. It
writes each yes/no question and proposes the final food. Structured output keeps
every proposal inside the list: each call's `food` field is an enum of the names
still available.

The engine has the **same session API and step shapes as the
[P10 decision-tree engine](../decision_tree/README.md)**. The P17 session wrapper
and the P19 client can run either one.

## Try it

```bash
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-09-29
python backend/manage.py demo_llm_engine --date 2026-09-29 --meal LU          # interactive
python backend/manage.py demo_llm_engine --date 2026-09-29 --smoke --output /tmp/llm_session.json
python backend/manage.py test question_engines.llm                            # no API key needed
```

The demo needs `GOOGLE_API_KEY` in the repo-root `.env` (see the
[DB setup guide](../../README.md)). The tests use a fake LLM.

## Use it

```python
import datetime
from menus.services import get_candidates
from question_engines.llm import LLMEngine

candidates = get_candidates(datetime.date(2026, 9, 29), meal="LU")
engine = LLMEngine(candidates, config={"max_questions": 10})   # Gemini from the environment
step = engine.start()
step = engine.answer(step["question_id"], "probably_yes")       # one of the six P10 answer IDs
if step["type"] == "guess":
    step = engine.feedback(step["guess_id"], accepted=False)    # "another menu": answers are kept
engine.diagnostics()   # question count, per-call LLM latency, attempts and fallbacks
engine.snapshot()      # JSON record; LLMEngine.from_snapshot(candidates, snapshot) restores it
```

| Method | Effect |
| --- | --- |
| `start()` / `next_step()` | Return the current step. Repeated reads do not call the LLM again |
| `answer(question_id, answer_id)` | Record the answer and ask the LLM for the next step |
| `feedback(guess_id, accepted)` | Accept the guess, or reject it: that menu leaves the list and the LLM continues |
| `recommend_now()` | Ask the LLM to propose a food now. A guess already on screen is returned unchanged |
| `undo()` | Restore the step before the last event, without calling the LLM |
| `snapshot()` / `from_snapshot(...)` | Persist and restore a session without calling the LLM |
| `diagnostics()` | Engineering logs for P20, not UI text |

Steps are `question`, `guess`, `recommendation` and `unavailable`, exactly as in
P10, with these differences:

- `target_kind` is always `"food"`: the LLM proposes single dishes, never groups.
- `question_id` is `q:llm-<n>`; question text is written by the LLM in English.
- Dishes with the same `display_name` are one choice for the LLM. The first one's
  `food_id` and offers stand for them.
- The default `max_questions` is 10 (`None` lets the LLM decide alone). At the
  limit, the next step is always a guess.

## Configuration and failures (P14)

| Variable | Default | Meaning |
| --- | --- | --- |
| `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) | required | Read when `LLMEngine` is built without `llm=`. Missing → `LLMConfigError` |
| `METCHU_LLM_MODEL` | `gemini-3.5-flash-lite` | Gemini model. Free-tier limits differ per model; see AI Studio |
| `METCHU_LLM_TIMEOUT` | `10` | Seconds per LLM call. Gemini rejects anything under 10 |

Each step makes up to `EngineConfig.max_attempts` (default 2) single-request calls.
When all of them time out, fail, or return invalid output (bad JSON, a menu outside
the list, an empty or repeated question), the session still continues:

- with the next unused fixed question from `prompt.FALLBACK_QUESTIONS`, or
- with a random available menu as a guess, when no question may be asked.

`diagnostics()["llm_calls"]` records `latency_ms`, `attempts` and `fallback`
(`"timeout"`, `"error"` or `"invalid_output"`) for each call. Every failed attempt
is logged as a warning. The API key never appears in logs or `repr()`.

## P17/P19 integration

`recommend/sessions.py` on `feat/p19-engine-ui-wiring` builds a
`DecisionTreeEngine`. The LLM engine drops in at the same place:

```python
from question_engines.llm import LLMEngine

self.engine = LLMEngine(candidates, config={"max_questions": self.max_questions})
```

The rest of the wrapper works unchanged: it validates `question_id` / `guess_id`,
reads `snapshot()["events"]` for `can_undo`, and only touches
`engine.catalog` for group guesses, which this engine never returns. Two things
are the wrapper's choice:

- `LLMConfigError` is raised when a session starts without an API key.
- An LLM step can take seconds. The client should show a loading state.
