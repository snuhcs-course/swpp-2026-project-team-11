# Metchu Android client

The app plays a recommendation session against the Django server. The question
engine runs on the server; the app draws whatever step the engine is on and
sends the user's taps back. The screens follow the first UI/UX design (i3-P4,
11/02): Jetpack Compose, the Pretendard font, one orange key color, English and
Korean text. The reinforcement learning (RL) engine asks by default; Settings can switch to
the decision tree. The LLM engine is shown but cannot be picked for now. The app
remembers the choice for the next session.

## Run it

1. Start the server from the repository root (see the root README for the
   one-time Python setup):

   ```bash
   python backend/manage.py migrate
   python backend/manage.py loaddata menus_v3_contract
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

### Google sign-in (optional)

Signing in with a username and password needs nothing more. "Continue with Google" and
Settings' "Link Google" appear only in a build with a web OAuth client ID; set it up once in
the Google Cloud project (Google Auth Platform):

1. **Branding / Audience**: an External app in testing, with the team's Google accounts as
   test users.
2. **Clients > Web application**: its client ID is what the app asks Google to address the
   sign-in token to, and what the server checks it against. No client secret is used.
3. **Clients > Android**: package `com.example.metchu` and the SHA-1 of the keystore that
   signs your build. Everyone who builds an APK adds one with their own SHA-1. Read it from
   Gradle, which names the keystore it actually signs with (`ANDROID_USER_HOME` can move the
   debug keystore away from `~/.android`):

   ```bash
   ./gradlew signingReport    # Variant: debug -> Store: ... and SHA1: ...
   ```

   With a SHA-1 the project does not know, Google's sheet closes without a token and the
   device log (`adb logcat -s Auth.Api.Credentials`) says `UNREGISTERED_ON_API_CONSOLE`.

4. Put the **web** client ID in `client/local.properties` and, as `METCHU_GOOGLE_CLIENT_ID`,
   in the server's `.env`, then rebuild:

   ```properties
   metchu.googleWebClientId=1234567890-abc.apps.googleusercontent.com
   ```

The device needs Google Play services and a Google account (an emulator with a Play Store
image works once you sign in to Google on it). Google shows its own account picker; closing
it changes nothing.

The app has no location permission and never reads or sends the phone's position
(i5-A1). The start sentence picks where to eat instead, one or more of: on campus (the
cafeterias), near 서울대입구역 and near 낙성대역 (i5-A7); the server keeps only the restaurants
of those areas (backend/README.md, "Areas", which also gives the rollout order: the server
before the APK). The start map centers on the first picked area: the campus or the
station. The result and group maps show the restaurants only: no user dot, distances,
walking times or locate button. Walking directions pass only the destination, and the
map app picks the start itself.

## Screens

| When | Screen | Actions |
| --- | --- | --- |
| first launch | Language (asked in both), then Account (log in or sign up, optional), then Allergies (the Settings chips and a Next button), then Start dimmed but for the globe and the gear (bottom-left), with a tip that both change there anytime | a language goes on at once; on Account, "Not now" goes on as a guest and signing in goes on by itself; ‹ on Allergies returns to Account (to Language once signed in); on the tip a tap anywhere, Back or "Got it" closes it for good, and the gear also opens Settings |
| no session | Start: "Today I'll have [lunch] [anywhere] [at any price] [for me]", a round start button, a faded map around the first picked area (the SNU administration building for campus, else the station) | the meal, the areas (장소 in Korean) and the price ranges open a small menu under them, without dimming the screen; the meal's menu closes on a pick, while areas (campus, 서울대입구역, 낙성대역) and price ranges (one to three ₩ signs) take one or more, each tap turning one on or off, and close on a tap elsewhere or Back; the sentence reads one area by name, two as "in two places" and all three as "anywhere", and one price range in words ("on a budget", "at a fair price", "for a treat"), two as their ₩ signs and all three as "at any price"; with no area or no price range the button turns grey, does not start and reads "Pick a place" or "Pick a price range" (장소를 선택해주세요, 가격을 선택해주세요); the small "?" beside the price shows the won each range covers; the globe (bottom-left) grows into the language menu; the gear beside it opens Settings; "Resume" (top-right) returns to a session left with home; "for me" / "with friends" switches to group mode, where the button creates a room (a guest names themselves first), chips under the sentence pick how long each question waits (10, 15, 30 or 60 s; 15 at first) and "Join with a code" (top-right) opens Join |
| gear | Settings: the account (signed out: "Log in or sign up"; signed in: the username, whether Google is linked, "Bookmarks", "History", "Link Google" and "Log out"), one chip per allergen (a picked one changes only its fill, so the chips never move), a note that the tags are AI estimates, the engine (decision tree, RL or LLM) | Back keeps the choices; there is no save button; "Log in or sign up" opens the Account screen, which returns here once signed in; "Bookmarks" and "History" open the account's lists |
| Bookmarks, History | The account's saved dishes (name and restaurant) or the dishes it was recommended (name, restaurant, date and meal), newest first | ‹ returns to Settings; a failed load offers "Try again"; the rows do nothing when tapped |
| Account | Log in or Create an account: username, password (twice to create one), the rules, "Continue with Google" in a build with a Google client ID | the line under the button switches between the two; errors show under the fields; the token is kept in its own preferences file, which backup leaves out |
| `question` | The current question under the past ones, one grey line each with the answer on the right; a five-step slider with "I'm not sure"; a progress bar | dragging along the slider or tapping a circle answers; a past question goes back to it; ‹ undoes (on the first question, leaves); home in the top-right corner; "Recommend now" floats bottom-right once there is an answer |
| `guess`, `recommendation` | Result: the dish (or a kind of dish with an example) over a map of its cafeterias, and a sheet with one or two sentences on why it suits the user and the cafeterias, one row per cafeteria | "Find another" (bottom-right) turns down the dish the server proposes now and asks on, whichever dish is shown; ‹ undoes; home in the top-right corner, with a bookmark button beside it when signed in that saves or removes the dish on view with the cafeteria chosen (the button fills at once and empties again if the server refuses); chips above the sheet switch between the dishes shown so far; a cafeteria row glides the map to it; the directions icon at its end (when the cafeteria is on the map) opens a walking route to it in Naver Map, else Kakao Map's web link (which Kakao hands to its app when installed); only the destination is passed and the map picks the start, with no route API in the app; the menu icon beside it lists what that cafeteria serves at that meal in a sheet built like the result sheet (its handle closes it; long menus scroll with faded edges), the proposed dish in orange; there is no ban link: a dish "Find another" turned down does not come back in the session unless ‹ goes back past it; the sheet's handle, dish name and description drag or tap it between folded, half and full |
| Join | Four code boxes filled from an in-app number pad, and a name field for a guest | "Join" turns orange once the code (and a guest's name) is there; ‹ returns to the start screen |
| room `lobby` | The code in large digits, "Send invite" (Android's share sheet), who is here with "Me" / "Host" and their allergies | the host's "Start · N" needs two people and spins, still orange, while the room starts (TalkBack reads it as loading); others see "The host will start"; ‹ or Back leaves the room |
| room `asking` | Members' circles across the top (orange ring and check once answered, never what), a bar running down the round's time (`round_seconds`, the host's pick), "Question n · answer within N s" with the seconds left on the right, the past rounds with this phone's answer, the shared question, the five-step scale, the rounds | an answer is final; a press still held when the round moves on answers nothing; then the bar turns grey and "Waiting for … · 9 s"; in the last 5 s without an answer the bar and count turn orange, the count pulses each second, the phone ticks once and "I'm not sure" is marked; at 0 the server answers "not sure" for the silent; the host's "Recommend now" appears after the first round; home or Back asks before leaving, since nobody can come back |
| room `done` | Map pins and chips for every restaurant the room has been shown (by name, at most 240 dp, longer names ending in "…"), the newest find first and each find in the server's order, in a row that scrolls sideways; a chip shows a thumb and the number who agree once anyone does (i5-P2); under "Today's lunch" (the meal picked at the start), each member's dish there with its price and "Great fit" / "Good fit", this phone's first, then the restaurant's other dishes; a round thumb (48 dp to tap) at the right of the restaurant's name, over "Agree n"; with two or more restaurants, an orange "Popular" tag on the chip of each one with the most votes (none before the first vote) | chips or pins switch restaurant; the directions icon under the name opens a walking route as on the result screen; the thumb agrees with the restaurant shown, turning orange, and a second tap takes it back, until the host decides; the host's "Find other places" (left of "Go here", while the server says `more`) adds restaurants the room has not been shown, with no votes yet, and every phone moves to the first new one and scrolls the chips back to the start; the earlier ones keep their votes, and members may still agree with them and the host may still choose one; the host's "Go here" decides, and every phone then opens "Meet here" once (i5-P17): a centered card with the restaurant and each member's dish and price, this phone's first, with "Start over" (leaves the room), "Directions" and "OK"; "Meet at …" stays at the bottom and opens the card again; home or Back asks before leaving until the host has decided |
| `unavailable` | Why nothing can be recommended today; with allergies saved, that no dish is known to be free of them and that Settings can change them | ‹ returns to the start screen |

The five circles send `no`, `probably_no`, `any`, `probably_yes` and `yes`, left
to right; "I'm not sure" sends `unknown`. The scale is drawn by the app for the
answer IDs the engines share (`AnswerId`); a circle whose ID the server does
not offer is dimmed. Pressing the slider brings a handle out of the middle that
follows the finger with a tick of haptic feedback per answer; letting go picks
it, and letting go well above or below the row cancels. The answer shows under
the question meanwhile; once picked, both shrink into the question's line in
the list, and going back plays this in reverse. When the next question comes,
in a session or a group round, the handle glides back into the middle circle in the
picked answer's color and fades out as the circles grow back.

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
screen can offer to resume it until a new one starts. The result's cafeteria list
is in the server's order; the session already holds only the picked areas. The
selected cafeteria is kept by name.

The meal starts at the next one the cafeterias serve (breakfast before 10,
lunch before 15, dinner after); one the user picks is kept until the app closes. The areas and price ranges (every one until the user changes them; the single area or price an app from before i5-A7 kept becomes its set), round time, engine and allergies are kept on
the phone (`SettingsStore`, `AllergyStore`, SharedPreferences). The language
follows the phone until the globe picks one (`AppCompatDelegate` per-app
locales). A new session asks the server for the app's language (`en` or `ko`), so
questions come in that language too. Food and cafeteria names are shown as the
server sends them, in Korean.

While nothing else is open (no sheet, tip or language menu), a
soft circle spreads from the start button three times to invite a tap. While a
session starts, the start screen searches: the sentence gives way to "Finding
your menu", which TalkBack reads out, the start button shrinks into a dot over
the first picked area with ripples spreading from it, and the map fills the screen, zoomed out to
the campus; the faded settings and language buttons cannot be reached meanwhile.
The search shows for at least 0.7 s, so a quick reply does not cut it short.
The pins on the result map have a thinner white ring (1.5 dp), to match the
dot on the start map.

A tapped answer stays filled while its request runs; other taps are ignored. A
request that takes more than 0.3 s shows a spinner, in the start button while a
room is created and at the end of the phase line on the question screen. A failed request shows a banner at the top. Retry is offered for transient failures. An unsupported start configuration stays on the start screen so the user can change Settings.
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
data/model/RoomState.kt             a group room as one member sees it
data/network/RoomApi.kt             Retrofit endpoints of the group rooms
data/repository/RecommendRepository.kt   the session requests; with RoomRepository the only classes that call Retrofit
data/repository/RoomRepository.kt   the room requests, with the member token
data/repository/AllergyStore.kt     the user's allergies, on this device
data/repository/SettingsStore.kt    the engine, areas, price ranges and round time choices, on this device
ui/main/MainActivity.kt             hosts the Compose app
ui/main/MetchuApp.kt                picks the screen for the session's step; the error banner
ui/main/RecommendViewModel.kt       session state, question history, loading and error LiveData
ui/start/                           start screen and the meal choice
ui/settings/                        allergies and engine
ui/question/                        question history, five-step scale, progress
ui/result/                          result map and sheet, walking directions, nothing to recommend
ui/group/                           group mode: join, lobby, shared question, restaurants; GroupViewModel polls the room
ui/common/                          shared buttons, pills, bottom and picker sheets
ui/theme/Theme.kt                   colors, font and text sizes of the design foundation board
```

The font is Pretendard (SIL Open Font License), subset to the 2,350 KS X 1001
Hangul syllables plus Latin and renamed MetchuSans, as the license's reserved
font name requires. Rarer syllables fall back to the system font. The license
is in `app/src/main/assets/licenses/pretendard-OFL.txt`.

## REST contract (`backend/recommend`)

| Request | Body | Effect |
| --- | --- | --- |
| `POST /api/sessions/` | `{"date"?, "meal"?, "engine"?, "allergies"?, "language"?, "areas"?, "price_levels"?}` | Android sends the engine selected in Settings (`decision_tree`, `rl` or `llm`), the meal (`BR`, `LU`, `DN` or the whole day), the app language (`en` or `ko`) and the picked `areas`, always and at least one: `campus` (the cafeterias), `snu_station` and `nakseongdae` (the restaurants around that station). No location is sent. `price_levels` (one or more of 1 to 3, always sent) keeps only dishes in one of those bands; all three is any price (backend/README.md, "Price range"). Apps from before i5-A7 send one `area` and `price_level`, which the server still reads. Any area besides `campus` rejects the LLM engine (400 `area_llm_unsupported`). With `allergies`, dishes whose tags are missing or contain an excluded allergen are withheld. |
| `POST /api/sessions/prewarm/` | `{"meal"?, "areas"?, "allergies"?}` | 204. The start screen sends it when it opens and when the meal, areas or allergies change, outside group mode and while an area is picked, so the server has built the restaurant catalogue before Start. It creates no session |
| `GET /api/sessions/<id>/` | | Current state |
| `POST /api/sessions/<id>/answer/` | `{"question_id", "answer_id"}` | Answer the current question |
| `POST /api/sessions/<id>/feedback/` | `{"guess_id", "accepted"}` | Accept or reject the current guess |
| `POST /api/sessions/<id>/recommend-now/` | | Ask for a guess immediately |
| `POST /api/sessions/<id>/undo/` | | Go back one step |
| `POST /api/sessions/<id>/ban/` | `{"food_id" or "food_group", "banned"}` | Keep one dish, or every dish of a `food_group`, out of the rest of the session (`banned: false` lets it back). The step on screen stays; the next action that would show the dish turns it down, and an undo that would goes back further. Bans end with the session. The phone no longer calls it (i4-A10, i4-A22) |
| `GET /api/sessions/<id>/reason/` | | `{"food_id", "reason", "source"}`: why the dish on screen suits the user, in the session's language. `source` is `llm`, or `template` when the server has no key or the LLM failed. With no dish on screen, a 409 `stale_step` |
| `GET /api/sessions/<id>/menu/?restaurant=<name>` | | `{"restaurant", "dishes"}`: the session's dishes that restaurant serves, each `{"food_id", "display_name", "meal", "price"}`, breakfast first and by name within a meal. Dishes withheld for an allergy, outside the areas or by price are not listed. An unknown restaurant has no dishes |

The group room requests (backend/README.md "Group rooms") go through `RoomApi` and
`RoomRepository`, on a client that hides `Authorization` and `X-Member-Token` in the debug log.
Creating or joining sends the account token when signed in and a name otherwise; creating also
sends the host's `areas`, `price_levels` and `round_seconds` (`RoomApi.ROUND_SECONDS`, matching the server's choices). Every later
request sends the member token the reply returned. `GroupViewModel` polls `GET /api/rooms/<code>/`
every second until the host has decided, and counts the seconds left down between replies. A
409 `stale_step` (the round moved on) waits for the next poll; `room_not_found` or `not_member`
on a poll takes the phone back to the start screen. No poll is sent while this phone's own
request is out, and a poll reply is dropped once a newer request has gone out, since it may
hold the room from before; of the requests, only the latest one's reply is shown (i4-A13).
A vote does not block the other taps, so "Go here" right after one still goes out.
When a poll shows that this phone's member has taken over as host, the top banner says
"You're the host now" until the next request, and the host's controls appear (i5-P8).

The account requests (`backend/accounts`, see backend/README.md "Accounts") go through
`AuthApi` and `AuthRepository`, on a separate HTTP client that logs headers only, with the
token hidden, so no password reaches the debug log:

| Request | Body | Effect |
| --- | --- | --- |
| `POST /api/auth/signup/`, `POST /api/auth/login/` | `{"username", "password"}` | `{"token", "user"}`; the app keeps both |
| `POST /api/auth/google/` | `{"id_token"}` from Google's picker | `{"token", "user", "created"}` |
| `POST /api/auth/google/link/` | `{"id_token"}`, with `Authorization: Token <token>` | `{"user"}` with `google_email` |
| `GET /api/auth/me/` | `Authorization: Token <token>` | `{"user"}`; asked once at launch for a saved account |
| `POST /api/auth/logout/` | `Authorization: Token <token>` | 204; the app forgets the account even if this fails |
| `GET /api/auth/bookmarks/` | `Authorization: Token <token>` | `{"bookmarks"}`; read when a result or the Bookmarks list opens. The result shows a dish as saved by its restaurant and name, not its food ID, which can change from day to day |
| `POST /api/auth/bookmarks/` | `{"food_id", "display_name", "restaurant"}`, with the token | `{"bookmark"}`, 201 or 200 if saved already |
| `DELETE /api/auth/bookmarks/<id>/` | `Authorization: Token <token>` | 204 |
| `GET /api/auth/history/` | `Authorization: Token <token>` | `{"history"}`; read when the History list opens |

A 401 `not_authenticated`, at launch or on any account request, signs the app out. The launch
check also takes the server's view of the account, such as a Google link made on another device.
An unreachable server or any other error at launch keeps the account signed in. A signed-in
phone sends the token when it creates a solo session (`POST /api/sessions/`), so the server adds
each dish the session proposes to the account's history; the later session requests do not send it.

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
Each of a food's `offers` is `{"restaurant", "meal", "price", "lat", "lng"}`;
`price` is null when the menu lists none, and `lat` or `lng` is null when the cafeteria's
location is not known (the app then leaves it off the map).

Errors are `{"error": {"code", "message"}}`:

| Status | `code` | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Invalid request fields. A rejected start request stays on the start screen so the user can change settings, including when an older server does not recognize RL. |
| 400 | `area_llm_unsupported` | The LLM engine with any area besides campus. The app says to change the engine in Settings and offers no retry |
| 404 | `session_not_found` | Unknown session; the app returns to the start screen |
| 409 | `stale_step` | The question or guess is no longer current. The body also carries `state`, and the app redraws from it |
| 503 | `engine_unavailable` | The selected engine is unavailable (for example missing LLM configuration or invalid stored features for RL). The app stays on the start screen and offers no retry |

Server behavior to know about:

- Sessions are kept in server memory. Restarting `runserver` ends them.
- There is no question limit by default: `max_questions` is `null`, the engine
  asks until it is ready to guess, and the user can tap "Just recommend
  something" at any time. `METCHU_MAX_QUESTIONS=N` makes the selected engine guess
  after N answers.
- Station areas keep only the restaurants inside those stations' circles before the
  engine starts; `candidate_count` counts what is left. If nothing is left, the
  session is `unavailable` with `empty_candidates`.
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
| Account API (`backend/accounts/tests`) | `python -m pytest backend/accounts` | Python only |
| JSON contract, repository, ViewModels (also the group room's), progress, meal and cafeteria list (`app/src/test`) | `./gradlew testDebugUnitTest` | JDK only |
| The Compose screens against a fake server (`app/src/androidTest`) | `./gradlew connectedDebugAndroidTest` | a running emulator or phone |

`app/src/sharedTest` holds what the two client suites share: a fake `ApiService`
and `resources/contract/*.json`, replies captured from the real server on the
2026-09-29 snapshot, since replaced by 2026-11-02 (the reply shape has not changed),
with `METCHU_MAX_QUESTIONS=10` (`question_llm.json` with a
scripted LLM in place of Gemini). `menu.json` was captured on 2026-11-02 (301동식당, lunch), so
it includes a set listed once at its whole price. `question.json` and `question_rl.json` were recaptured on 2026-11-18 from the `menus_v3_contract`
fixture; `recommendation.json` from a general session with two mapped sales menus of one restaurant.
The `auth_*.json` and account `error_*.json` replies were captured on 2026-11-10 from a local
server on its own SQLite database (the token is that throwaway database's); `FakeAuthApi` stands
in for the account server. `history.json` was captured
on 2026-11-25 the same way after a signed-in cafeteria lunch session on the `menus_v3_contract`
fixture that showed two dishes; `bookmark_saved.json` and `bookmarks.json` were recaptured the
same day the same way, with the bookmark `id`, after both dishes were bookmarked.
The `room_*.json` replies and `error_room_not_found.json` were captured on 2026-11-13 from the
room views on a local SQLite with the 2026-11-02 snapshot (two members, cafeteria lunch, the
host answering three seconds in; the member token replaced by `member-token`). `room_done.json` was
recaptured on 2026-11-17 the same way with votes (the guest agreeing with the second restaurant, the
host with both) and a location on campus. `more` (i4-A13) is false in every capture: the lobby
and the questions have no result yet, and `room_done.json` is after the host's decision.
`batch` (i5-P2) is 0 in `room_done.json`, as the server sends for a room that has not asked for other
places; replaying the capture on the server after i5-P2 gave the same field at the same place. Its
picks and dishes have since changed with the engine, so the rest was kept as captured.
On 2026-11-28 (i5-A1) `distance_m` was removed from every captured offer and pick, as the
server no longer sends it. Replaying a cafeteria and a 서울대입구역 session and a decided room on
the server after i5-A1 gave offers and picks with exactly the keys the edited files keep; the
rest of each file is as captured.
`FakeRoomApi` stands in for the room server; `hold()` keeps a reply back to deliver replies out
of order.
The client tests decode those files, so they are the client's
side of the REST contract. Recapture them when the server's JSON changes.

The server tests include seeded random sessions on the fixture. A failure prints
its seed; rerun that seed to reproduce it. `test_public_access.py` runs
`serve_public` against scripted stand-ins for the server and cloudflared, so it
needs neither cloudflared nor the network.

## Canonical personal menus (i4-P19)

The personal result can name a canonical type while each offer carries its actual `menu_name` and `restaurant_code`. The result sheet shows that sales name under its restaurant; price and location remain those of the offer. Both solo and group questions now use the server's shared 53-feature English/Korean wording. Group inference remains DT-only. Optional offer fields preserve older response decoding.
