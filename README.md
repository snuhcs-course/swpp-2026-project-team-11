# Metchu! — Iteration 4 Demo (SNU SWPP 2026 Team 11)

Metchu helps you decide what to eat around SNU. It asks a few quick questions
and proposes a dish from that day's menus, with the places that sell it, how far
they are and why it suits you. Friends can also decide together in Group Mode.
This branch is the working demo at the end of Iteration 4: `main` at `af9a46e`
plus the demo videos and this guide.

## Demo videos

Two screen recordings of the app on an Android phone, made for the Iteration 4
TA meeting on November 18, 2026 against the team server:

- [Group Mode](docs/iteration-4-demo-group.mov) (1 min 10 s). Friends join one
  room with a 4-digit code, answer the same questions in timed rounds, and get
  up to two restaurants with a dish for each member that avoids their
  allergies. Members vote, and the host decides.
- [Solo mode on the menu-category engine](docs/iteration-4-demo-solo.mov)
  (24 s). The app proposes a kind of dish first, then lists the places that sell
  it with each place's own menu name and price.

They were recorded before the walking directions (#61) and the "anywhere"
default (#63) were merged, so those two do not appear. The setup below uses a
small committed fixture, so its dishes and places differ from the videos. Earlier
recordings are on the
[`iteration-3-demo`](https://github.com/snuhcs-course/swpp-2026-project-team-11/tree/iteration-3-demo)
branch and in [docs/iteration-1-demo.mp4](docs/iteration-1-demo.mp4).

## How to run the demo

The demo has two parts: a Django server that runs the question engines and the
group rooms, and an Android app that plays a session against it.

You need:

- Python 3.12 (with [uv](https://docs.astral.sh/uv/), which reads
  `pyproject.toml`) or Python 3.12 or newer with pip
- JDK 21 (the Android build fails on JDK 25)
- Android Studio with an emulator (we used "Medium Phone", API 36) or an
  Android phone; two devices for Group Mode
- Optional: a Google Maps API key for the maps, and an OpenRouter API key for
  LLM-written explanations

### 1. Start the server

Clone the demo branch and set up Python from the repository root:

```bash
git clone --branch iteration-4-demo https://github.com/snuhcs-course/swpp-2026-project-team-11.git
cd swpp-2026-project-team-11
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

The RL engine, the app's default, runs on PyTorch (CPU). On Linux, add
`--extra-index-url https://download.pytorch.org/whl/cpu` to the `pip install`
line to get the CPU build instead of the much larger CUDA one. With uv instead of
pip, skip the venv and prefix each `python` command below with
`uv run --isolated --locked`; it uses the CPU build everywhere.

Then fill a local database and start the server:

```bash
export DATABASE_URL=                 # local SQLite, even if .env names the shared DB
python backend/manage.py migrate
python backend/manage.py loaddata menus_v3_contract
METCHU_MENU_DATE=2026-11-02 python backend/manage.py runserver 0.0.0.0:8000
```

`loaddata` fills the local database with a small synthetic fixture in the
current 53-feature format: 15 places and 127 dishes on November 2, 2026, already
tagged, so no API key is needed. The fixture has only that day, which is why the
server is started with `METCHU_MENU_DATE`.

On PowerShell, use `$env:DATABASE_URL = " "` and set
`$env:METCHU_MENU_DATE = "2026-11-02"` before running the server command without
its inline `METCHU_MENU_DATE=...` prefix.

Leave this terminal open. To check the server from a second terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/ -H 'Content-Type: application/json' \
  -d '{"meal": "LU", "engine": "rl", "source": "all", "language": "en"}'
```

It answers with a JSON session whose `candidate_count` is 103 and whose first
`step` is a question.

### 2. (Optional) Add API keys

The decision tree and RL engines need no key. With an
[OpenRouter](https://openrouter.ai/keys) key (ask the team), the result screen's
explanation is written by an LLM; without one, the server writes it from a
template. Put the key in a `.env` file in the repository root **before**
starting the server:

```bash
cp .env.example .env      # then set OPENROUTER_API_KEY=your-key
```

`.env` is gitignored. If the server is already running, stop it with Ctrl-C and
run the last command of step 1 again. Signing in with Google also needs a Google
client ID on both sides; see [backend/README.md](backend/README.md), "Accounts".
Signing in is optional, and a username and password work without it.

### 3. Run the app

Open the `client/` folder (not the repository root) in Android Studio and wait
for the Gradle sync. The app defaults to the team server, which is up only while
the team runs it. To use the local server from step 1 instead, create the
untracked `client/local.properties` with:

```properties
metchu.baseUrl=http://10.0.2.2:8000/
metchu.mapsApiKey=AIza...            # optional; without it the maps are left out
```

Then start an emulator from the Device Manager and run the `app` configuration.
From a terminal instead, with the emulator running and JDK 21 as `JAVA_HOME`:

```bash
cd client && ./gradlew installDebug
```

On the emulator, set a position near campus under Extended controls > Location
(for example 37.4600, 126.9520) so the app can show distances. For Group Mode,
start a second emulator and install the app there too; both reach the local
server at `10.0.2.2`.

For a phone on a USB cable, run `adb reverse tcp:8000 tcp:8000` and use
`metchu.baseUrl=http://127.0.0.1:8000/`. From another network, start the server
behind a Cloudflare Tunnel with `manage.py serve_public`. The
[client guide](client/README.md#run-it) covers these setups and the Maps key.

If the app shows "Could not reach the server", the server is not running or
`metchu.baseUrl` points somewhere else.

### 4. Try it

**Alone**

1. On the first launch, pick the language, skip the account step with
   **Not now** (or sign up), pick any allergies and tap **Next**, then close the
   tip. Allow the location when asked.
2. The start screen reads "Today I'll have [lunch] [anywhere] [at any price]
   [for me]". Tap a word to change the meal, the distance (nearby means within a
   10-minute walk) or the price range, then tap the round **Start** button. The
   gear opens Settings: the account, allergies and the question engine (RL by
   default, or the decision tree).
3. Answer each question with the five circles (no … yes) or **I'm not sure**.
   ‹ undoes the last step, and tapping an earlier question goes back to it.
   **Recommend now** asks for a proposal right away.
4. The result shows the dish, why it suits you, and the places that serve it
   with their own menu names, prices and walking distances. Tap a place to move
   the map to it. Its directions icon opens a walking route in Naver Map or Kakao
   Map, and its menu icon lists what it serves.
5. Tap **Find another** to turn the dish down and go on; a dish turned down does
   not come back in the session. Home returns to the start screen, where
   **Resume** continues the session.

**With friends** (two devices)

1. On the first device, tap "for me" and choose "with friends", then create a
   room (a guest types a name first). The lobby shows a 4-digit code and
   **Send invite**.
2. On the second device, choose "with friends", tap **Join with a code** and
   enter the code. Each member's allergies are listed in the lobby.
3. The host taps **Start · 2** (a room holds 2 to 8). Everyone answers the same
   question within 15 seconds; a member who does not answer counts as "not
   sure". After at most four rounds, every phone shows the same one or two
   restaurants and each member's dish there.
4. Members tap the thumb to agree with a restaurant; the most agreed one gets a
   "Popular" tag. The host can ask for other restaurants with **Find another**,
   and **Go here** decides: every phone then shows "Meet at …".

Questions and dishes depend on your answers and allergies.

### Tests

```bash
python -m pytest backend                                           # no API key or network
(cd client && ./gradlew testDebugUnitTest)                          # JDK 21
(cd client && ./gradlew connectedDebugAndroidTest)                  # needs an emulator
```

## Environment we used

| | |
| --- | --- |
| OS | macOS 26 (Apple Silicon) and Windows 11 |
| Server | Python 3.12 (uv) or 3.13, Django 5.2, PyTorch 2.14 on CPU, local SQLite or the shared Supabase Postgres |
| Team server | A mini PC run by the team, reached through an ngrok address (the app's default) |
| Question engines | RL (the default) and decision tree for solo sessions; Group Mode uses the decision tree; the LLM engine stays on the server |
| Menu features | 53 features per dish; restaurant menus mapped to 267 dish types; computed ahead of time, no key needed for the demo |
| Android build | Android Studio 2026.1, Gradle 8.13, Android Gradle Plugin 8.12, Kotlin 2.0.21, Jetpack Compose, JDK 21 |
| Android target | `compileSdk` 36, `minSdk` 26, Google Maps SDK for Android |
| Devices | Emulator "Medium Phone" (API 36); Samsung Galaxy S23 (Android 14) in the in-class UAT |

## What the demo demonstrates

### Features implemented

- **Menu database.** A daily job fetches, cleans and stores the SNU cafeteria
  menus, and each menu is tagged with food features and possible allergens.
  Restaurants near 서울대입구역 and 낙성대역 come from Naver Place menus, each
  sales menu mapped to one of 267 dish types.
- **Question engines behind one API.** An RL policy (the default) and a decision
  tree pick the next question from the dishes' features and decide when to
  propose. Both run without an API key.
- **Group Mode.** Rooms for 2 to 8 people with shared, timed rounds, a pick that
  every member can eat, votes, and the host's decision.
- **Accounts.** Optional sign-up with a username and password, or Google.
- **Android app.** Solo and group flows in English and Korean, with allergies,
  meal, distance and price filters, a map-based result, the places' menus and
  walking directions.

### Major progress during Iteration 4

- **Group Mode (P3 #50, P9 #51, A19 #58, A13 #56, A16 #57).** The group engine
  asks the whole room one shared question per round and suggests up to two
  restaurants, each with every member's closest dish that avoids their
  allergies. Rooms, 15-second rounds, a lobby with invites, member votes with a
  "Popular" tag, and the host's "Find another" and "Go here" followed. UAT
  testers asked for a say in the final choice, which led to the votes.
- **Menu-category engine (P19 #60).** 7,698 restaurant sales menus are mapped to
  267 dish types with 53 features each, and a new RL policy is trained on them.
  A dish type is proposed once, however many places sell it, and each place
  keeps its real menu name and price. UAT testers had seen the same dish under
  many names.
- **Accounts (P6 #49).** Username and password or Google sign-in; signing in is
  optional.
- **Faster start (A4 #53, A7 #54).** The restaurant catalogue is cached and
  prepared before Start, and the map searches while the first question loads.
- **Result screen.** A price range filter (A23 #59), walking directions in
  Naver Map or Kakao Map (A25 #61), one "Find another" instead of separate ban
  links (A10, A22 #55), and "anywhere" as the default distance (A27 #63).
- **Testing.** The in-class UAT on November 16: 115 of 122 step results
  accepted by two testers from other teams, with every requirement meeting its
  criteria. See the
  [UAT analysis](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki/UAT-Analysis-%E2%80%93-Iteration-4)
  and [Testing Documentation](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki/Testing-Documentation).

### Known limits

- The committed fixture is small and synthetic. Real menus need a menu fetch,
  and the restaurant menus also need the dish-type mapping import
  ([docs/personal-catalogue.md](docs/personal-catalogue.md)); the team server
  has both.
- Allergen tags are LLM estimates from menu names, not the restaurants' data.
- Sessions and rooms live in server memory; restarting the server ends them.
- Group Mode uses the decision tree only.
- Recommendation quality has so far been measured with simulated users and in
  the UAT; it has not yet been measured with real users over time.

## Agent workflow

Codex and Claude Code share [AGENTS.md](AGENTS.md). The
[agent workflow](docs/agent-workflow.md) describes the local task and usage records,
Google Sheets setup, PR/wiki handoff and iteration reports. Start with
`python tools/harness.py --help`; local records and credentials stay out of Git.

## Component guides

- [Android client and REST contract](client/README.md)
- [Menu database, accounts and feature extraction](backend/README.md)
- [Personal RL and the mapped catalogue](docs/personal-catalogue.md)
- [Group engine](backend/question_engines/group/README.md)
- [Decision-tree engine](backend/question_engines/decision_tree/README.md)
- [LLM engine](backend/question_engines/llm/README.md)
- [Requirements and design Wiki](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki)
