# Metchu Android client

One screen that plays a recommendation session against the Django server. The
P10 question engine runs on the server; the app renders whatever step the
engine is on and sends the user's taps back.

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
| no session | Start screen with a meal selector | Start |
| `question` | Progress, question text, one button per answer option | answer, Back, Just recommend something |
| `guess` | The proposed dish with its cafeterias and prices. A group guess shows the group name, one example dish and the other dishes in the group | yes, no, Back |
| `recommendation` | The accepted dish and where to get it | Start over |
| `unavailable` | Why nothing can be recommended | Start over |

A request in flight dims the screen and ignores taps. A failed request shows a
banner that stays until the next request, with Try again.

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
| `POST /api/sessions/` | `{"date"?, "meal"?}` | Start a session. `meal` is `BR`, `LU`, `DN` or omitted for the whole day |
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

`step` is the engine's step as documented in the
[P10 engine guide](../backend/question_engines/decision_tree/README.md), with one
change: a group's `food_ids` is replaced by `members`, a list of
`{"food_id", "display_name"}`.

Errors are `{"error": {"code", "message"}}`:

| Status | `code` | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Malformed body, unknown answer ID, bad date or meal |
| 404 | `session_not_found` | Unknown session; the app returns to the start screen |
| 409 | `stale_step` | The question or guess is no longer current. The body also carries `state`, and the app redraws from it |

Server behavior to know about:

- Sessions are kept in server memory. Restarting `runserver` ends them.
- The engine has no question limit of its own. The server makes it guess after
  `METCHU_MAX_QUESTIONS` answers (default 10; 0 removes the cap).
- `recommend-now` on a guess, or after the session has ended, changes nothing
  and returns the current state.

Tests: `python backend/manage.py test recommend`.
