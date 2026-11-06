# Metchu! — Iteration 3 Demo (SNU SWPP 2026 Team 11)

Metchu helps you decide what to eat around SNU. It asks a few quick questions
and proposes a dish from that day's menus, with where to get it, how far it is
and why it suits you. This branch is the working demo at the end of Iteration 3:
`main` at `e36f6ea` plus the demo video and this guide.

## Demo video

[Watch the Iteration 3 demo video](docs/iteration-3-demo.mp4) (1 min 41 s, a
screen recording of the app on an Android phone, in Korean).

It was recorded on November 4, 2026 against the team server, with that day's
lunch menu:

1. **First launch** (0:00). The app asks for the language, then for allergies,
   and points to the globe and gear buttons where both change later. It then
   asks for the location, to show nearby cafeterias and their distances.
2. **Settings** (about 0:22). Egg is picked as an allergy, so no dish that may
   contain egg is proposed. The question engine is RL, the default; the LLM
   engine is shown but unavailable for now.
3. **Questions** (from about 0:35). The start screen reads "오늘 점심은 가까운
   식당에서 먹을래요" over a map. The RL engine asks questions such as "빵으로 된
   식사가 당기나요?", and each is answered on a five-step slider. The answered
   questions stay listed above the current one.
4. **Result** (about 0:55). The app proposes 핫소마요치킨 at 버거운버거, 388 m
   away (a 5-minute walk), on a map with the user's position. A sentence explains
   why it fits the answers, and the menu icon lists everything that cafeteria
   serves for lunch.
5. **Find another** (from about 1:05). The user turns the dish down. After a
   second chicken dish (칠리마요치킨), they keep chicken out for the rest of the
   session. More questions lead to C코너 셀프라면 at 예술계식당 and then
   양념치킨버거. Chips above the sheet switch between the dishes proposed so far.

The setup below uses the committed November 2 snapshot, so its dishes and
questions differ from the video. The [Iteration 1 recording](docs/iteration-1-demo.mp4)
is kept for comparison; the Iteration 2 one is on the
[`iteration-2-demo`](https://github.com/snuhcs-course/swpp-2026-project-team-11/tree/iteration-2-demo) branch.

## How to run the demo

The demo has two parts: a Django server that runs the question engines, and an
Android app that plays a session against it.

You need:

- Python 3.11 or newer
- JDK 21 (the Android build fails on JDK 25)
- Android Studio with an emulator (we used "Medium Phone", API 36) or an
  Android phone
- Optional: a Google Maps API key for the maps, and an OpenRouter API key for
  LLM-written explanations

### 1. Start the server

Clone the demo branch, then run the server from the repository root:

```bash
git clone --branch iteration-3-demo https://github.com/snuhcs-course/swpp-2026-project-team-11.git
cd swpp-2026-project-team-11
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
export DATABASE_URL=                 # local SQLite, even if .env names the shared DB
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-11-02
METCHU_MENU_DATE=2026-11-02 python backend/manage.py runserver 0.0.0.0:8000
```

`loaddata` fills the local database with the shared snapshot: the SNU
cafeteria menus of November 2, 2026, already preprocessed and tagged with food
features and allergens, so no API key is needed. The snapshot has only that
day, which is why the server is started with `METCHU_MENU_DATE`.

On PowerShell, use `$env:DATABASE_URL = " "` and set
`$env:METCHU_MENU_DATE = "2026-11-02"` before running the server command without
its inline `METCHU_MENU_DATE=...` prefix.

Leave this terminal open. To check the server from a second terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/ -H 'Content-Type: application/json' \
  -d '{"meal": "LU", "engine": "rl", "source": "all", "language": "ko"}'
```

It answers with a JSON session whose first `step` is a question (in Korean).

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
run the last command of step 1 again.

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
(for example 37.4600, 126.9520) so the app can show distances.

For a phone on a USB cable, run `adb reverse tcp:8000 tcp:8000` and use
`metchu.baseUrl=http://127.0.0.1:8000/`. From another network, start the server
behind a Cloudflare Tunnel with `manage.py serve_public`. The
[client guide](client/README.md#run-it) covers these setups and the Maps key.

If the app shows "Could not reach the server", the server is not running or
`metchu.baseUrl` points somewhere else.

### 4. Try it

The steps follow the video:

1. On the first launch, pick the language, pick any allergies and tap
   **Next**, then close the tip. Allow the location when asked.
2. On the start screen, tap the meal to choose **Lunch** and the place to choose
   nearby or all cafeterias, then tap the round **Start** button. The gear opens
   Settings: allergies and the question engine (RL by default, or the decision
   tree).
3. Answer each question with the five circles (no … yes) or **I'm not sure**.
   ‹ undoes the last step, and tapping an earlier question goes back to it.
   **Recommend now** asks for a proposal right away.
4. The result shows the dish, why it suits you, and the cafeterias that serve
   it with prices and walking distances. Tap a cafeteria to move the map to it;
   the menu icon lists its other dishes.
5. Tap **Find another** to turn the dish down and go on. Once a food group
   appears twice among the last three proposals, a link keeps it out of the rest
   of the session. Home returns to the start screen.

Questions and dishes depend on your answers and allergies.

Without the app, the decision tree also runs in a terminal:

```bash
python backend/manage.py demo_decision_tree --date 2026-11-02 --meal LU
```

### Tests

```bash
python -m pytest backend                                           # no API key or network
(cd client && ./gradlew testDebugUnitTest)                          # JDK 21
(cd client && ./gradlew connectedDebugAndroidTest)                  # needs an emulator
```

## Environment we used

| | |
| --- | --- |
| OS | macOS 26.6.2 (Apple Silicon) |
| Server | Python 3.14, Django 5.2, local SQLite or the shared Supabase Postgres; Python 3.11 in GitHub Actions |
| Team server | A mini PC run by the team, reached through an ngrok address (the app's default) |
| Question engines | Decision tree and RL in Python + NumPy on CPU; LLM engine (`google/gemini-3.5-flash-lite` through OpenRouter), currently disabled in the app |
| Menu preprocessing and features | Configurable Google/OpenAI model through LangChain; already computed in the shared fixture |
| Android build | Android Studio 2026.1, Gradle 8.13, Android Gradle Plugin 8.12, Kotlin 2.0.21, Jetpack Compose, JDK 21 |
| Android target | `compileSdk` 36, `minSdk` 26, Google Maps SDK for Android |
| Devices | Emulator "Medium Phone" (API 36) and an Android phone (the video) |

## What the demo demonstrates

### Features implemented

- **Menu database.** A daily GitHub Actions job fetches, cleans and stores the
  SNU cafeteria menus, and each sales menu is tagged with food features and possible
  allergens by an LLM. Restaurants near 서울대입구역 and 낙성대역 are imported
  from Naver Place menus in the same format.
- **Question engines behind one API.** A feature-only reinforcement learning
  (RL) policy, the default, and a decision tree pick the next question from the
  dishes' features and decide when to propose. Both run without an API key. The
  LLM engine is kept on the server but disabled in the app for now.
- **REST session API.** Start a session, answer, turn down a proposal, ask for a
  recommendation now, undo, keep a dish or food group out, list a cafeteria's
  menu, and get an explanation of the proposed dish.
- **Android app.** First-launch language and allergy setup, a start screen with
  the meal and distance choices over a map, a question screen with a five-step
  slider and the answer history, and a result screen with a map, the
  explanation, and the cafeterias with prices and walking distances. English and
  Korean throughout.

### Major progress during Iteration 3

- **Redesigned app (P4, #19, #40).** Rebuilt every screen from the UI/UX design:
  the sentence-style start screen, the five-step slider, a map-based result
  screen with a draggable sheet, and floating actions. Fixes from a heuristic
  evaluation (#29), faster answer taps (#28) and a first-launch setup (#35)
  followed.
- **Location, maps and distances (P15, #16, #20, #33).** The result map shows
  the cafeterias serving the dish with the user's position, and the list shows
  distances and walking times. "Nearby" keeps cafeterias within 800 m.
- **Allergy filter (#18).** Dishes that may contain a picked allergen are never
  proposed, using LLM-estimated allergen tags with a note to check at the
  cafeteria.
- **More places to eat (P9, #22, #23, #30, #42).** Added the restaurants near
  서울대입구역 and 낙성대역 from Naver Place menus, the 300동 food court
  구시아푸드마켓 from a fixed board, and sessions over all of them at once.
- **RL engine and real sales menus (P12, #27, #31, #34, #38, #44).** Added a
  feature-only RL policy, now the app's default. Candidates are the actual
  menus as the cafeterias sell them, with their real names and prices, scored
  from source-scoped feature profiles.
- **Decision tree at scale (P10, #43).** The decision tree no longer builds
  quadratic matrices for sales-menu catalogs, so a session over about 6,300
  combined menus starts in seconds.
- **Explanations, language and control (#25, #26, #36, #37).** Each session runs
  in the app's language; the result explains why the dish fits; a cafeteria's
  full menu opens from the result; a food group can be kept out of the session.
- **Team workflow (P3, #15, #24, #41).** A shared harness for agent task
  records, usage and the schedule sheet; `main` became the integration branch;
  the app defaults to the team server.

### Known limits

- Only the 2026-11-02 cafeteria menus are included as a loadable fixture. The
  restaurants near the stations and other dates need a menu fetch and a model
  API key for preprocessing and tagging, so the local demo shows the campus
  cafeterias only.
- Allergen tags are LLM estimates from menu names, not the cafeterias' data.
- Sessions live in server memory; restarting the server ends them.
- The API has no login. It is meant for a demo, not a public service.
- Engine comparisons so far use simulated users. The study with real students
  was moved to Iteration 4.

## Agent workflow

Codex and Claude Code share [AGENTS.md](AGENTS.md). The
[agent workflow](docs/agent-workflow.md) describes the local task and usage records,
Google Sheets setup, PR/wiki handoff and iteration reports. Start with
`python tools/harness.py --help`; local records and credentials stay out of Git.

## Component guides

- [Android client and REST contract](client/README.md)
- [Menu database and feature extraction](backend/README.md)
- [Decision-tree engine](backend/question_engines/decision_tree/README.md)
- [LLM engine](backend/question_engines/llm/README.md)
- [Requirements and design Wiki](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki)
