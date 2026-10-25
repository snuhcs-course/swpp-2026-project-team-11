# Metchu! — Iteration 2 Demo (SNU SWPP 2026 Team 11)

Metchu helps you decide what to eat at the SNU cafeterias. It asks a few quick
questions and proposes a dish from that day's menu. This branch is the working
demo at the end of Iteration 2. The `iteration-2-demo` branch starts from the
remote `MVP` integration branch and includes the demo video and this run guide.

## Demo video

[Watch the Iteration 2 demo video](docs/iteration-2-demo.mp4) (55 seconds).

The recording shows both engines on the October 20, 2026 dinner menu
(85 dishes): the decision tree asks questions for a hamburger craving and
proposes 치즈버거; the LLM engine writes questions for a 짬뽕 craving.

The setup below uses the committed September 29 snapshot, so its dishes and
questions differ from the video. Follow [step 4](#4-try-it) to try both engines. The
[Iteration 1 recording](docs/iteration-1-demo.mp4) is also kept for comparison.

## How to run the demo

The demo has two parts: a Django server that runs the question engines, and an
Android app that plays a session against it. Both run on one machine; the app
runs on an Android emulator.

You need:

- Python 3.11 or newer
- JDK 21 (the Android build fails on JDK 25)
- Android Studio with an emulator (we used "Medium Phone", API 36)
- Only for the LLM half of the demo: an OpenRouter API key

### 1. Start the server

Clone the demo branch, then run the server from the repository root:

```bash
git clone --branch iteration-2-demo https://github.com/snuhcs-course/swpp-2026-project-team-11.git
cd swpp-2026-project-team-11
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
export DATABASE_URL=                # local SQLite, even if .env names the shared DB
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-09-29
METCHU_MENU_DATE=2026-09-29 python backend/manage.py runserver 0.0.0.0:8000
```

`loaddata` fills the local database with the shared menu snapshot, so no API key
is needed for the menu. The snapshot only has September 29, 2026, which is why
the server is started with `METCHU_MENU_DATE`.

On PowerShell, use `$env:DATABASE_URL = " "` and set
`$env:METCHU_MENU_DATE = "2026-09-29"` before running the server command without
its inline `METCHU_MENU_DATE=...` prefix.

Leave this terminal open. To check the server from a second terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/ -H 'Content-Type: application/json' -d '{"meal": "LU"}'
```

It answers with a JSON session whose `candidate_count` is 193 and whose first
`step` is a question.

### 2. (Optional) Enable the LLM engine

The decision-tree engine needs nothing else. To try the LLM engine as well, get
an [OpenRouter](https://openrouter.ai/keys) key from the team and put it in a
`.env` file in the repository root **before** starting the server:

```bash
cp .env.example .env      # then set OPENROUTER_API_KEY=your-key
```

`.env` is gitignored. If the server is already running, stop it with Ctrl-C and
run the last command of step 1 again. Without a key, choosing LLM in the app
shows a message that the LLM engine is not set up, and the decision tree keeps
working.

### 3. Run the app

Open the `client/` folder (not the repository root) in Android Studio, wait for
the Gradle sync, start an emulator from the Device Manager, and run the `app`
configuration. The emulator reaches the server on the same machine at
`http://10.0.2.2:8000/`, which is the app's default, so nothing has to be
configured.

From a terminal instead, with the emulator running and JDK 21 as `JAVA_HOME`
(the build fails on JDK 25):

```bash
cd client && ./gradlew installDebug
```

If the app shows "Could not reach the server", the server from step 1 is not
running, or `client/local.properties` has a `metchu.baseUrl` left over from
another setup; remove that line and run the app again.

For a phone on a USB cable, forward the port and point the app at it in the
untracked `client/local.properties`, then run the app again:

```bash
adb reverse tcp:8000 tcp:8000
```

```properties
metchu.baseUrl=http://127.0.0.1:8000/
```

From another network (mobile data, another Wi-Fi), start the server behind a
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
instead of `runserver`. It needs `cloudflared` on the server machine, but no port
forwarding or Cloudflare account:

```bash
brew install cloudflared                 # once; Windows: winget install Cloudflare.cloudflared
METCHU_MENU_DATE=2026-09-29 python backend/manage.py serve_public --write-client-config
```

It prints a public `https://<random>.trycloudflare.com/` address and writes it to
`client/local.properties`; rebuild the app to use it. The address changes on
every start. The [client guide](client/README.md#from-another-network-cloudflare-tunnel)
covers the details and a fixed address with a named tunnel.

### 4. Try it

Try the key app features:

1. On the start screen, keep **Lunch** and **Decision tree**, and tap **Start**.
   The top line shows `2026-09-29 · LUNCH · 193 DISHES · DECISION TREE`.
2. Answer the questions with any of the six buttons. **Back** undoes the last
   step. There is no fixed number of questions: the engine proposes something
   when further questions do not justify their cost. **Just recommend something**
   asks for a proposal right away.
3. The default decision-tree policy proposes a concrete dish; the reference
   policies can also propose a kind of dish with an example. Tap
   **No, something else** to keep going, or **Yes, I'll have this** to accept.
4. The result shows the dish, the cafeteria and the price. Tap **Start over**.
5. Choose **LLM** and tap **Start** to play the same menu with the LLM writing
   the questions (needs the key from step 2). Each step takes a few seconds.

Questions and dishes depend on your answers, and the LLM engine can word its
questions differently each time.

Without the app, the same engines run in a terminal:

```bash
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU
python backend/manage.py demo_llm_engine --date 2026-09-29 --meal LU     # needs the key
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
| Server | Python 3.14.3, Django 5.2, local SQLite; Python 3.11 in GitHub Actions |
| LLM questions | Gemini (`google/gemini-3.5-flash-lite`) through OpenRouter; requires `OPENROUTER_API_KEY` |
| Menu preprocessing and features | Configurable Google/OpenAI model through LangChain; already computed in the shared fixture |
| Android build | Android Studio 2026.1, Gradle 8.13, Android Gradle Plugin 8.12, Kotlin 2.0.21, JDK 21 |
| Android target | `compileSdk` 36, `minSdk` 26 |
| Devices | Emulator "Medium Phone" (API 36) and a Galaxy Note20 (SM-N981N) over USB |

## What the demo demonstrates

### Features implemented

- **Cafeteria menu database.** A day's SNU cafeteria menu is fetched, cleaned
  and stored, and each dish is tagged with food features by an LLM. The shared
  snapshot holds the result for one day.
- **Decision-tree question engine.** Picks the next question from the dishes'
  features, updates preference fit after each answer, and proposes a dish when
  more questions do not justify their cost. Runs without any API key.
- **LLM question engine.** Gemini writes each question from the dish names
  alone and proposes a dish. If a call fails or times out, the session goes on
  with a fixed question or a random dish.
- **REST session API.** One API runs either engine: start a session, answer,
  accept or reject a proposal, ask for a recommendation now, and undo.
- **Android app.** One screen that follows the session: start, question,
  proposal, result. The start screen chooses the meal and the engine.

### Major progress during Iteration 2

- **Daily menu pipeline and shared storage (P7/P8).** Added cached menu-line
  preprocessing, a reviewed fixed-menu catalog, Supabase support, and a daily
  GitHub Actions pipeline that fetches, preprocesses and tags menus.
- **Feature extraction v2 and decision-tree integration (P11).** Expanded to
  32 name-based mean/std measurements plus deterministic `meal_variety`,
  distinguished set meals, and added version-consistent catalog loading. The
  decision tree now uses preference fit and expected decision value for its
  default question and stopping policy. The included September 29 fixture
  keeps its 23 legacy features and works without re-extraction.
- **LLM engine improvements (P3/P4).** Moved question generation to OpenRouter
  and added prompt guidance, a summary of settled answers, and repeated-question
  checks with retries. Failed calls still fall back to playable steps.
- **Feature evaluation (P12).** Added integrity, distribution, stability,
  triplet, human-rating and downstream evaluation tools. The committed
  [feature report](feature_benchmark_results/2026-10-20-luna/report.md) includes
  966 records across seven runs; human-reference and downstream sections await
  completed ratings.
- **Engine comparison (P16/P17).** Added paired scenarios, simulated users,
  acceptance, question-count, latency and cost metrics, and human-study tooling.
  The saved [engine report](engine_benchmark_results/2026-10-20/benchmark_report.md)
  covers 100 scenarios, three repeats per engine, and 600 sessions. Read the
  [benchmark guide](backend/question_engines/benchmark/README.md#results) for
  provenance and limitations.
- **Development workflow.** Added backend pytest coverage and CI, configurable
  menu models, and optional Cloudflare Tunnel support for phone demos.

### Known limits

- Only the 2026-09-29 menu is included as a loadable database fixture. Other
  dates need a menu fetch and a configured model API key for preprocessing and
  tagging. Saved benchmark scenarios and reports use October data separately.
- Sessions live in server memory; restarting the server ends them.
- The API has no login. It is meant for a local demo, not a public server.
- Benchmark acceptance rates come from simulated users. Human-rating and user
  study tooling is implemented; the committed reports do not establish real
  student acceptance rates.

## More detail

- [Android client and REST contract](client/README.md)
- [Menu database and feature extraction](backend/README.md)
- [Decision-tree engine](backend/question_engines/decision_tree/README.md)
- [LLM engine](backend/question_engines/llm/README.md)
- [Question engine benchmark](backend/question_engines/benchmark/README.md)
- [Requirements and design Wiki](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki)
