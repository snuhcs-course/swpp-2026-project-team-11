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
   `OPENROUTER_API_KEY` in the repo-root `.env` (see `.env.example`) before starting
   the server; without it, choosing LLM in the app shows an error and the
   decision tree keeps working.

2. Open the `client/` folder in Android Studio, wait for the Gradle sync, and
   run the `app` configuration on an emulator. Command line:
   `./gradlew installDebug`.

The emulator reaches the host machine at `http://10.0.2.2:8000/`, which is the
default. For a physical phone on the same Wi-Fi, add your machine's LAN address
to the untracked `client/local.properties`, and start the server with that
address in `METCHU_ALLOWED_HOSTS` (comma-separated, or set it in `.env`):

```properties
metchu.baseUrl=http://192.168.0.3:8000/
```

```bash
METCHU_ALLOWED_HOSTS=192.168.0.3 python backend/manage.py runserver 0.0.0.0:8000
```

A phone on a USB cable needs no shared network. Forward the phone's port 8000 to
your machine and point the app at the phone's own localhost, which is already in
`ALLOWED_HOSTS`:

```bash
adb reverse tcp:8000 tcp:8000
```

```properties
metchu.baseUrl=http://127.0.0.1:8000/
```

The forwarding is lost when the cable is replugged or adb restarts; the app then
shows "Could not reach the server". Run the `adb reverse` command again.

### From another network (Cloudflare Tunnel)

The setups above need the phone next to the server machine. `serve_public` runs
the server together with a Cloudflare Tunnel, which gives it a public https
address that works from mobile data or any other network. Install
[`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
on the server machine once (`brew install cloudflared`,
`winget install Cloudflare.cloudflared`), then start the server with this command
instead of `runserver`:

```bash
METCHU_MENU_DATE=2026-09-29 python backend/manage.py serve_public --write-client-config
```

```
Public address: https://calm-red-fox-demo.trycloudflare.com/
Check it:       https://calm-red-fox-demo.trycloudflare.com/api/health/
App setting:    metchu.baseUrl=https://calm-red-fox-demo.trycloudflare.com/   (client/local.properties)
```

1. Open the "Check it" address in any browser; it shows `{"status": "ok"}`. The
   address is printed once the tunnel has connected, but some networks find a new
   address only after about a minute. On SNU campus Wi-Fi, a lookup before then fails
   and the campus DNS remembers the failure for 60 s, so wait a minute before the
   first try, and if it fails, wait another minute rather than retrying at once.
2. `--write-client-config` has replaced `metchu.baseUrl` in `client/local.properties`
   with the address (without the flag, copy the printed "App setting" line there).
   Rebuild and install the app from `client/` (`./gradlew installDebug`, JDK 21); it
   now works on any network for as long as the command keeps running.
3. Ctrl-C, `kill` or closing the terminal stops the server and the tunnel. The app
   then shows "Could not reach the server".
4. To go back to the emulator or a USB phone, delete the `metchu.baseUrl` line (or
   set it back) and rebuild the app.

Things to know:

- **The address changes on every start** of a quick tunnel, so the app must be
  rebuilt each time. For a fixed address, use a named tunnel (below).
- **Anyone who has the address can use the server**, including the LLM engine and
  so your Gemini quota. Share it only with the team and stop the command when done.
  `serve_public` turns Django's `DEBUG` off and keeps the server itself bound to
  `127.0.0.1`; `--debug` turns `DEBUG` back on.
- The emulator and `adb reverse` setups keep working while it runs, on `--port`
  (default 8000).
- `-v 2` shows cloudflared's own log, for when no address appears.
- Mobile data, or Android's Private DNS (Settings > Network > Private DNS, e.g.
  `one.one.one.one`), avoids the slow campus DNS.
- Quick tunnels do not start if `~/.cloudflared/config.yml` exists; rename it or
  use a named tunnel.

#### A fixed address (named tunnel)

This needs a Cloudflare account with a domain on it. In the Zero Trust dashboard,
create a tunnel (Networks > Tunnels), add a public hostname such as
`metchu.example.com` with the service `http://localhost:8000`, and copy the
tunnel's token. Put both in the repo-root `.env`:

```
METCHU_TUNNEL_TOKEN=eyJh...
METCHU_PUBLIC_URL=https://metchu.example.com
```

`serve_public` then runs that tunnel instead of a quick one, and the app can be
built once with `metchu.baseUrl=https://metchu.example.com/`. The token is a
secret like the API key: keep it in `.env` only.

### Cafeteria map (Google Maps key)

The result screen shows the cafeterias serving the dish on a Google Map. It
needs a Google Maps API key with **Maps SDK for Android** enabled (Google Cloud
Console > APIs & Services). Put it in the untracked `client/local.properties`
and rebuild:

```properties
metchu.mapsApiKey=AIza...
```

Without the key the app works as before and leaves the map out. The key ends up
inside the APK, so restrict it to Android apps (package `com.example.metchu` and
your signing certificate's SHA-1) in the console; never commit it. The map asks
for location permission the first time it appears, to show the user's own
position; if the user declines, it shows only the cafeterias. On the emulator,
set a position under Extended controls > Location.

## Screens

| Engine step | What the app shows | Actions |
| --- | --- | --- |
| no session | Start screen with a meal selector and an engine selector (Decision tree / LLM) | Start |
| `question` | Progress, question text, one button per answer option | answer, Back, Just recommend something |
| `guess` | The proposed dish with its cafeterias and prices. A group guess shows the group name, one example dish and the other dishes in the group | yes, no, Back |
| `recommendation` | The accepted dish, where to get it and, with a Maps key, a map of those cafeterias | Start over |
| `unavailable` | Why nothing can be recommended | Start over |

A tapped button gives a light haptic tick, sinks slightly and stays highlighted
while its request runs; the other buttons fade and ignore taps. A failed request shows a
banner that stays until the next request, with Try again.

The line under the header shows the date, meal, number of dishes and the engine
the server ran. Both engines use the same screens. Two things differ in use:

- An LLM step waits for the LLM, usually a few seconds and at most about 20
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
ui/main/CafeteriaPin.kt             which cafeterias the result map marks
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
  "max_questions": null,
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
Each of a food's `offers` is `{"restaurant", "meal", "price", "lat", "lng"}`;
`price` is null when the menu lists none, and `lat`/`lng` are null together
when the cafeteria has no location.

Errors are `{"error": {"code", "message"}}`:

| Status | `code` | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Malformed body, unknown answer ID, bad date, meal or engine |
| 404 | `session_not_found` | Unknown session; the app returns to the start screen |
| 409 | `stale_step` | The question or guess is no longer current. The body also carries `state`, and the app redraws from it |
| 503 | `engine_unavailable` | `engine` was `llm` and the server has no `OPENROUTER_API_KEY` (or a malformed LLM setting). The app stays on the start screen |

Server behavior to know about:

- Sessions are kept in server memory. Restarting `runserver` ends them.
- There is no question limit by default: `max_questions` is `null`, the engine
  asks until it is ready to guess, and the user can tap "Just recommend
  something" at any time. `METCHU_MAX_QUESTIONS=N` makes either engine guess
  after N answers.
- Requests for one session run one at a time. A request repeated while an LLM
  step is still running waits for it and then gets `stale_step` with the
  current state, so a retry after a timeout never answers twice.
- `undo` has no such check: sent twice, it goes back two steps. After a failed
  Back the app's Try again therefore reads the state first, and sends `undo`
  again only if the server is still on the step the screen shows.
- `recommend-now` on a guess, or after the session has ended, changes nothing
  and returns the current state.

## Tests

| What | Command | Needs |
| --- | --- | --- |
| REST API and `serve_public` (`backend/recommend/tests`) | `python -m pytest backend/recommend` | Python only |
| JSON contract, repository and ViewModel (`app/src/test`) | `./gradlew testDebugUnitTest` | JDK only |
| The screen against a fake server (`app/src/androidTest`) | `./gradlew connectedDebugAndroidTest` | a running emulator or phone |

`app/src/sharedTest` holds what the two client suites share: a fake `ApiService`
and `resources/contract/*.json`, replies captured from the real server on the
2026-09-29 fixture with `METCHU_MAX_QUESTIONS=10` (`question_llm.json` with a
scripted LLM in place of Gemini).
The client tests decode those files, so they are the client's
side of the REST contract. Recapture them when the server's JSON changes.

The server tests include seeded random sessions on the fixture. A failure prints
its seed; rerun that seed to reproduce it. `test_public_access.py` runs
`serve_public` against scripted stand-ins for the server and cloudflared, so it
needs neither cloudflared nor the network.
