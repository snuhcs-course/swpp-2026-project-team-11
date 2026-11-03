# Metchu Android client

The app plays a recommendation session against the Django server. The question
engine runs on the server; the app draws whatever step the engine is on and
sends the user's taps back. The screens follow the first UI/UX design (i3-P4,
11/02): Jetpack Compose, the Pretendard font, one orange key color, English and
Korean text. In Settings, choose the decision tree, reinforcement learning (RL)
or LLM engine. The app remembers the choice for the next session.

## Run it

1. Start the server from the repository root (see the root README for the
   one-time Python setup):

   ```bash
   python backend/manage.py migrate
   python backend/manage.py loaddata menus_2026-11-02
   METCHU_MENU_DATE=2026-11-02 python backend/manage.py runserver 0.0.0.0:8000
   ```

   The shared fixture only has November 2. Without `METCHU_MENU_DATE` the
   server uses today's date in Seoul and the app shows "Nothing to recommend"
   unless that day's menu has been fetched and tagged.

   The shared fixture works with the decision tree and RL; RL runs on CPU without a
   model API key. For the LLM engine, put `OPENROUTER_API_KEY` in the repo-root
   `.env` (see `.env.example`) before starting the server; without it, choosing LLM
   in the app shows an error and the decision tree keeps working.

2. Open the `client/` folder in Android Studio, wait for the Gradle sync, and
   run the `app` configuration on an emulator. Command line:
   `./gradlew installDebug`.

The app defaults to the team's mini PC at `https://theology-panning-custody.ngrok-free.dev/`. To use
your local server from an emulator instead, set the following in the untracked
`client/local.properties` and rebuild:

```properties
metchu.baseUrl=http://10.0.2.2:8000/
```

For a physical phone on the same Wi-Fi, set your machine's LAN address instead,
and start the local server with that address in `METCHU_ALLOWED_HOSTS`
(comma-separated, or set it in `.env`):

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
METCHU_MENU_DATE=2026-11-02 python backend/manage.py serve_public --write-client-config
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
4. To return to the team server, remove `metchu.baseUrl` and rebuild. For an
   emulator or USB phone using a local server, set the corresponding URL above.

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

### Maps (Google Maps key)

The start screen shows a still map around the user under the start button, and
the result screen shows the cafeterias serving the dish on a Google map, in
Google's own map style. Both need a Google Maps API key with **Maps SDK for
Android** enabled (Google Cloud Console > APIs & Services). Put it in the
untracked `client/local.properties` and rebuild:

```properties
metchu.mapsApiKey=AIza...
```

Without the key the app works and leaves both maps out (a plain grey area on
the result screen). The key ends up inside the APK, so restrict it to Android
apps (package `com.example.metchu` and your signing certificate's SHA-1) in the
console; never commit it. The Maps terms require Google's logo to stay visible; the
result map keeps it just above the sheet with map padding.

Once per launch until it is allowed, the start screen says why it needs location
(on the first launch, after the settings tip is closed)
and, on **Continue**, asks for it. With it, a new session sends where the
device is: a current fix, or the last known location when none comes within 3
seconds (the start button shows it is loading meanwhile); the server then gives
each cafeteria's `distance_m`. The start map centers on the user, the result map
shows the user's position and fits it with the cafeterias (once, when the first
fix arrives, and only within 3 km of one, so a phone off campus keeps the
map on the cafeterias), and the cafeteria list shows distances and walking
times, nearest first. Without it the start map shows the middle of campus, the
session starts without a location and the list has no distances. On the
emulator, set a position under Extended controls > Location (for example
37.4600, 126.9520).

## Screens

| When | Screen | Actions |
| --- | --- | --- |
| first launch | Language (asked in both), then Allergies (the Settings chips and a Next button), then Start dimmed but for the globe and the gear (bottom-left), with a tip that both change there anytime | a language goes on at once; ‹ on Allergies returns to Language; on the tip a tap anywhere, Back or "Got it" closes it for good, and the gear also opens Settings |
| no session | Start: "Today I'll have [lunch] [nearby]", a round start button, a faded map around the user, or around the SNU administration building until location is allowed | the meal and the distance open a small menu under them, without dimming the screen; the globe (bottom-left) grows into the language menu; the gear beside it opens Settings; "Resume" (top-right) returns to a session left with home |
| gear | Settings: one chip per allergen (a picked one changes only its fill, so the chips never move), a note that the tags are AI estimates, the engine (decision tree, RL or LLM) | Back keeps the choices; there is no save button |
| `question` | The current question under the past ones, one grey line each with the answer on the right; a five-step slider with "I'm not sure"; a progress bar | dragging along the slider or tapping a circle answers; a past question goes back to it; ‹ undoes (on the first question, leaves); home in the top-right corner; "Recommend now" floats bottom-right once there is an answer |
| `guess`, `recommendation` | Result: the dish (or a kind of dish with an example) over a map of its cafeterias, and a sheet with one or two sentences on why it suits the user, a ban link and the cafeterias, one row per cafeteria | "Find another" (bottom-right) turns down the dish the server proposes now and asks on, whichever dish is shown; ‹ undoes; home in the top-right corner; chips above the sheet switch between the dishes shown so far; a cafeteria row glides the map to it, and the menu icon at its end lists what that cafeteria serves at that meal, the proposed dish in orange; once a food group makes up two of the last three proposals, "Don't suggest any <group>" keeps that group out of the rest of the session, even after ‹ (a dish without a group offers "Don't suggest this dish" at once), and turns into Undo; a new session starts without bans; the locate button centers the map on the user, then turns it with the phone; the sheet's handle, dish name and description drag or tap it between folded, half and full |
| `unavailable` | Why nothing can be recommended today; with allergies saved, that no dish is known to be free of them and that Settings can change them | ‹ returns to the start screen |

The five circles send `no`, `probably_no`, `any`, `probably_yes` and `yes`, left
to right; "I'm not sure" sends `unknown`. The scale is drawn by the app for the
answer IDs the engines share (`AnswerId`); a circle whose ID the server does
not offer is dimmed. Pressing the slider brings a handle out of the middle that
follows the finger with a tick of haptic feedback per answer; letting go picks
it, and letting go well above or below the row cancels. The answer shows under
the question meanwhile; once picked, both shrink into the question's line in
the list, and going back plays this in reverse.

The server keeps no question texts, so `RecommendViewModel` remembers the
answered questions and trims the list to the step's `question_count` after
every reply, also when a lost reply is retried and the server answers with
`stale_step`. Tapping a past question sends `undo` until the server is back on
it. A picked answer is held for 0.45 s before it is sent, and is dropped if Back
moved the session meanwhile. The progress bar fills by `1 − 0.72^answers` (at least answers ÷
`max_questions` when the server caps them), up to 95 %.

The app fetches a reason after displaying a proposal and fetches it again if
the user changes the answers and sees the same proposal. With `OPENROUTER_API_KEY`
set, a reason request for any engine can make up to two model calls. Without the
key, or without evidence that a dish fits the user's answers, the server can
give a template explanation. Until it arrives, a pulsing line holds its place under the
dish; a network failure leaves the reason out.

"Find another" is `feedback` with `accepted: false`: the result screen shows a
`guess`, and the app never accepts one. Leaving with "Start over" simply drops
the session; home keeps a session with an answer or a dish in it so the start
screen can offer to resume it until a new one starts. The server cuts no distance by default (`METCHU_MAX_DISTANCE_M`), so
"nearby" is applied to the result's cafeteria list on the phone: cafeterias
within 800 m (a 10-minute walk at 80 m/min, straight line). Distances come from
the phone's current position, or the server's `distance_m` until the phone has
one. If none is that close, all are listed with a note; if no distance is known,
all are listed under a note that the location is unknown. The selected cafeteria
is kept by name, so it stays put when the list re-sorts as the user moves.

The meal starts at the next one the cafeterias serve (breakfast before 10,
lunch before 15, dinner after); one the user picks is kept until the app closes. The distance, engine and allergies are kept on
the phone (`SettingsStore`, `AllergyStore`, SharedPreferences). The language
follows the phone until the globe picks one (`AppCompatDelegate` per-app
locales). A new session asks the server for the app's language (`en` or `ko`), so
questions come in that language too. Food and cafeteria names are shown as the
server sends them, in Korean.

A tapped answer stays filled while its request runs; other taps are ignored. A
request that takes more than 0.3 s shows a spinner, in the start button while a
session starts and at the end of the phase line on the question screen. A failed request shows a banner at the top. Retry is offered for transient failures. An unsupported start configuration stays on the start screen so the user can change Settings.
Screens are white under a transparent navigation bar; scrolling ones fade into
white above it. Screens change with 0.3 s fades. An answered question shrinks
into the list and the next one fades in below it; going from a question to a result, the
question fades upward and the map, sheet, text and buttons enter in turn.

An LLM step waits for the LLM, usually a few seconds and at most about 20 (two
10-second attempts) before the server falls back to a fixed question or a
random dish. The app's read timeout is 30 seconds; raise it in
`RetrofitInstance.kt` if you raise `METCHU_LLM_TIMEOUT`. The LLM engine proposes
single dishes only, never a group.

## Structure

```
data/model/SessionState.kt          JSON shapes returned by the server, and the answer IDs
data/model/Allergen.kt              the allergens the server accepts (backend/menus/allergens.py)
data/network/ApiService.kt          Retrofit endpoints and request bodies
data/network/RetrofitInstance.kt    server address and HTTP client
data/location/LocationSource.kt     where the device is when a session starts
data/repository/RecommendRepository.kt   the only class that calls Retrofit
data/repository/AllergyStore.kt     the user's allergies, on this device
data/repository/SettingsStore.kt    the engine and the distance choice, on this device
ui/main/MainActivity.kt             hosts the Compose app
ui/main/MetchuApp.kt                picks the screen for the session's step; the error banner
ui/main/RecommendViewModel.kt       session state, question history, loading and error LiveData
ui/start/                           start screen and the meal choice
ui/settings/                        allergies and engine
ui/question/                        question history, five-step scale, progress
ui/result/                          result map and sheet, cafeteria distances, nothing to recommend
ui/common/                          shared buttons, pills, bottom and picker sheets, location
ui/theme/Theme.kt                   colors, font and text sizes of the design foundation board
```

The font is Pretendard (SIL Open Font License), subset to the 2,350 KS X 1001
Hangul syllables plus Latin and renamed MetchuSans, as the license's reserved
font name requires. Rarer syllables fall back to the system font. The license
is in `app/src/main/assets/licenses/pretendard-OFL.txt`.

## REST contract (`backend/recommend`)

| Request | Body | Effect |
| --- | --- | --- |
| `POST /api/sessions/` | `{"date"?, "meal"?, "engine"?, "location"?, "allergies"?, "language"?, "source"?, "distance_scope"?}` | Android sends the engine selected in Settings (`decision_tree`, `rl` or `llm`), the meal (`BR`, `LU`, `DN` or the whole day), and the app language (`en` or `ko`). Both distance choices send `source: "all"` to combine cafeteria and restaurant menus for DT or RL. `distance_scope: "near"` filters offers within 800 m straight-line distance before recommendation when location is known; without location it includes all. `distance_scope: "any"` applies no cutoff. General and all sources reject the LLM engine. `location` is the user's `{"lat", "lng"}`. With `allergies`, dishes whose tags are missing or contain an excluded allergen are withheld. |
| `GET /api/sessions/<id>/` | | Current state |
| `POST /api/sessions/<id>/answer/` | `{"question_id", "answer_id"}` | Answer the current question |
| `POST /api/sessions/<id>/feedback/` | `{"guess_id", "accepted"}` | Accept or reject the current guess |
| `POST /api/sessions/<id>/recommend-now/` | | Ask for a guess immediately |
| `POST /api/sessions/<id>/undo/` | | Go back one step |
| `POST /api/sessions/<id>/ban/` | `{"food_id" or "food_group", "banned"}` | Keep one dish, or every dish of a `food_group`, out of the rest of the session (`banned: false` lets it back). The step on screen stays; the next action that would show the dish turns it down, and an undo that would goes back further. Bans end with the session |
| `GET /api/sessions/<id>/reason/` | | `{"food_id", "reason", "source"}`: why the dish on screen suits the user, in the session's language. `source` is `llm`, or `template` when the server has no key or the LLM failed. With no dish on screen, a 409 `stale_step` |
| `GET /api/sessions/<id>/menu/?restaurant=<name>` | | `{"restaurant", "dishes"}`: the session's dishes that restaurant serves, each `{"food_id", "display_name", "meal", "price"}`, breakfast first and by name within a meal. Dishes withheld for an allergy or by distance are not listed. An unknown restaurant has no dishes |

Every success returns the same session state:

```json
{
  "session_id": "b3e73addc47a4a54b6cb08e1d575f770",
  "engine": "decision_tree",
  "date": "2026-11-02",
  "meal": "LU",
  "language": "en",
  "candidate_count": 107,
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
Each of a food's `offers` is `{"restaurant", "meal", "price", "lat", "lng", "distance_m"}`;
`price` is null when the menu lists none, `lat` or `lng` is null when the cafeteria's
location is not known (the app then leaves it off the map), and `distance_m` is the straight-line distance in meters
from the session's `location`, null when either is unknown.

Errors are `{"error": {"code", "message"}}`:

| Status | `code` | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Invalid request fields. A rejected start request stays on the start screen so the user can change settings, including when an older server does not recognize RL. |
| 404 | `session_not_found` | Unknown session; the app returns to the start screen |
| 409 | `stale_step` | The question or guess is no longer current. The body also carries `state`, and the app redraws from it |
| 503 | `engine_unavailable` | The selected engine is unavailable (for example missing LLM configuration or invalid stored features for RL). The app stays on the start screen and offers no retry |

Server behavior to know about:

- Sessions are kept in server memory. Restarting `runserver` ends them.
- There is no question limit by default: `max_questions` is `null`, the engine
  asks until it is ready to guess, and the user can tap "Just recommend
  something" at any time. `METCHU_MAX_QUESTIONS=N` makes the selected engine guess
  after N answers.
- There is no distance cutoff by default. `METCHU_MAX_DISTANCE_M=N` leaves out
  cafeterias more than N meters from the session's `location`, and dishes served
  nowhere closer, before the engine starts; `candidate_count` counts what is
  left. Sessions without a location and cafeterias without coordinates are not
  cut. If everything is cut, the session is `unavailable` with `empty_candidates`.
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
| JSON contract, repository, ViewModel, progress, meal and cafeteria list (`app/src/test`) | `./gradlew testDebugUnitTest` | JDK only |
| The Compose screens against a fake server (`app/src/androidTest`) | `./gradlew connectedDebugAndroidTest` | a running emulator or phone |

`app/src/sharedTest` holds what the two client suites share: a fake `ApiService`
and `resources/contract/*.json`, replies captured from the real server on the
2026-09-29 snapshot, since replaced by 2026-11-02 (the reply shape has not changed),
with `METCHU_MAX_QUESTIONS=10` (`question_llm.json` with a
scripted LLM in place of Gemini). `menu.json` was captured on 2026-11-02 (301동식당, lunch), so
it includes a set listed once at its whole price. The RL question fixture was captured from Django with three v2 cafeteria dishes.
The client tests decode those files, so they are the client's
side of the REST contract. Recapture them when the server's JSON changes.

The server tests include seeded random sessions on the fixture. A failure prints
its seed; rerun that seed to reproduce it. `test_public_access.py` runs
`serve_public` against scripted stand-ins for the server and cloudflared, so it
needs neither cloudflared nor the network.
