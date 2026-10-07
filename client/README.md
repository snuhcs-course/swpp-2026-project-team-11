# Metchu Android client

One screen that plays a recommendation session against the Django server. The
question engine runs on the server; the app renders whatever step the engine is
on and sends the user's taps back. The start screen chooses between the two
engines, the P10 decision tree and the P13/P14 LLM engine, so they can be
compared on the same menu.

## Run it

1. Start the server from the repository root (see the root README for the
   one-time Python setup):

   ```bash
   python backend/manage.py migrate
   python backend/manage.py loaddata menus_2026-09-29
   METCHU_MENU_DATE=2026-09-29 python backend/manage.py runserver 0.0.0.0:8000
   ```

   The shared fixture only has September 29. Without `METCHU_MENU_DATE` the
   server uses today's date in Seoul and the app shows "Nothing to recommend"
   unless that day's menu has been fetched and tagged.

   The decision tree needs nothing else. For the LLM engine, put
   `GOOGLE_API_KEY` in the repo-root `.env` (see `.env.example`) before starting
   the server; without it, choosing LLM in the app shows an error and the
   decision tree keeps working.

2. Open the `client/` folder in Android Studio, wait for the Gradle sync, and
   run the `app` configuration on an emulator. Command line:
   `./gradlew installDebug`.

The emulator reaches the host machine at `http://10.0.2.2:8000/`, which is the
default. For a physical phone on the same Wi-Fi, add your machine's LAN address
to the untracked `client/local.properties` and to `ALLOWED_HOSTS` in
`backend/metchu/settings.py`:

```properties
metchu.baseUrl=http://192.168.0.3:8000/
```

## Screens

| Engine step | What the app shows | Actions |
| --- | --- | --- |
| no session | Start screen with a meal selector and an engine selector (Decision tree / LLM) | Start |
| `question` | Progress, question text, one button per answer option | answer, Back, Just recommend something |
| `guess` | The proposed dish with its cafeterias and prices. A group guess shows the group name, one example dish and the other dishes in the group | yes, no, Back |
| `recommendation` | The accepted dish and where to get it | Start over |
| `unavailable` | Why nothing can be recommended | Start over |

A tapped button gives a light haptic tick, sinks slightly and stays highlighted
while its request runs; the other buttons fade and ignore taps. A failed request shows a
banner that stays until the next request, with Try again.

The line under the header shows the date, meal, number of dishes and the engine
the server ran. Both engines use the same screens. Two things differ in use:

- An LLM step waits for Gemini, usually a few seconds and at most about 20
  (two 10-second attempts) before the server falls back to a fixed question or
  a random dish. The app's read timeout is 30 seconds; raise it in
  `RetrofitInstance.kt` if you raise `METCHU_LLM_TIMEOUT`. Back never waits.
- The LLM engine proposes single dishes only, never a group.

Question text, answer labels and guess text are shown as the server sends them.
Food and cafeteria names stay in their source language.

## Structure

```
data/model/SessionState.kt          JSON shapes returned by the server
data/network/ApiService.kt          Retrofit endpoints and request bodies
data/network/RetrofitInstance.kt    server address and HTTP client
data/repository/RecommendRepository.kt   the only class that calls Retrofit
ui/main/RecommendViewModel.kt       session state, loading and error LiveData
ui/main/MainActivity.kt             draws the current step, forwards taps
```

## REST contract (`backend/recommend`)

| Request | Body | Effect |
| --- | --- | --- |
| `POST /api/sessions/` | `{"date"?, "meal"?, "engine"?}` | Start a session. `meal` is `BR`, `LU`, `DN` or omitted for the whole day. `engine` is `decision_tree` or `llm`; omitted, the server uses `METCHU_ENGINE` (default `decision_tree`) |
| `GET /api/sessions/<id>/` | | Current state |
| `POST /api/sessions/<id>/answer/` | `{"question_id", "answer_id"}` | Answer the current question |
| `POST /api/sessions/<id>/feedback/` | `{"guess_id", "accepted"}` | Accept or reject the current guess |
| `POST /api/sessions/<id>/recommend-now/` | | Ask for a guess immediately |
| `POST /api/sessions/<id>/undo/` | | Go back one step |

Every success returns the same session state:

```json
{
  "session_id": "b3e73addc47a4a54b6cb08e1d575f770",
  "engine": "decision_tree",
  "date": "2026-09-29",
  "meal": "LU",
  "candidate_count": 193,
  "max_questions": 10,
  "can_undo": false,
  "step": {"type": "question", "question_count": 0, "question_id": "q:chicken",
           "text": "Do you feel like chicken?", "options": [{"id": "yes", "label": "Yes, sounds good"}]}
}
```

`engine` is the engine this session runs. `step` is the engine's step as
documented in the
[P10 engine guide](../backend/question_engines/decision_tree/README.md), with one
change: a group's `food_ids` is replaced by `members`, a list of
`{"food_id", "display_name"}`. The
[LLM engine](../backend/question_engines/llm/README.md) returns the same step
shapes; its `question_id` is `q:llm-<n>` and it never sends a `group`.

Errors are `{"error": {"code", "message"}}`:

| Status | `code` | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Malformed body, unknown answer ID, bad date, meal or engine |
| 404 | `session_not_found` | Unknown session; the app returns to the start screen |
| 409 | `stale_step` | The question or guess is no longer current. The body also carries `state`, and the app redraws from it |
| 503 | `engine_unavailable` | `engine` was `llm` and the server has no `GOOGLE_API_KEY` (or a malformed LLM setting). The app stays on the start screen |

Server behavior to know about:

- Sessions are kept in server memory. Restarting `runserver` ends them.
- The server makes either engine guess after `METCHU_MAX_QUESTIONS` answers
  (default 10; 0 removes the cap).
- Requests for one session run one at a time. A request repeated while an LLM
  step is still running waits for it and then gets `stale_step` with the
  current state, so a retry after a timeout never answers twice.
- `recommend-now` on a guess, or after the session has ended, changes nothing
  and returns the current state.

## Tests

| What | Command | Needs |
| --- | --- | --- |
| REST API (`backend/recommend/tests`) | `python backend/manage.py test recommend` | Python only |
| JSON contract, repository and ViewModel (`app/src/test`) | `./gradlew testDebugUnitTest` | JDK only |
| The screen against a fake server (`app/src/androidTest`) | `./gradlew connectedDebugAndroidTest` | a running emulator or phone |

`app/src/sharedTest` holds what the two client suites share: a fake `ApiService`
and `resources/contract/*.json`, replies captured from the real server on the
2026-09-29 fixture (`question_llm.json` with a scripted LLM in place of Gemini).
The client tests decode those files, so they are the client's
side of the REST contract. Recapture them when the server's JSON changes.

The server tests include seeded random sessions on the fixture. A failure prints
its seed; rerun that seed to reproduce it.
