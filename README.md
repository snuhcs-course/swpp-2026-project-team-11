# Metchu! — Iteration 1 Demo (SNU SWPP 2026 Team 11)

Metchu helps you decide what to eat at the SNU cafeterias. It asks a few quick
questions and proposes a dish from that day's menu. This branch is the working
prototype at the end of Iteration 1.

## Demo video

_To be added._

## How to run the demo

The demo has two parts: a Django server that runs the question engines, and an
Android app that plays a session against it.

### 1. Start the server

Requires Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-09-29
METCHU_MENU_DATE=2026-09-29 python backend/manage.py runserver 0.0.0.0:8000
```

`loaddata` fills the local database with the shared menu snapshot, so no API key
is needed for the menu. The snapshot only has September 29, 2026, which is why
the server is started with `METCHU_MENU_DATE`.

### 2. (Optional) Enable the LLM engine

The decision-tree engine needs nothing else. To try the LLM engine as well, get
a key from [Google AI Studio](https://aistudio.google.com/apikey) and put it in
a `.env` file in the repository root **before** starting the server:

```bash
cp .env.example .env      # then set GOOGLE_API_KEY=your-key
```

`.env` is gitignored. Without a key, choosing LLM in the app shows an error and
the decision tree keeps working.

### 3. Run the app

Open the `client/` folder in Android Studio, wait for the Gradle sync, and run
the `app` configuration on an emulator. The emulator reaches the server at
`http://10.0.2.2:8000/`, which is the default.

For a phone on a USB cable, forward the port and point the app at it in the
untracked `client/local.properties`, then run the app again:

```bash
adb reverse tcp:8000 tcp:8000
```

```properties
metchu.baseUrl=http://127.0.0.1:8000/
```

### 4. Try it

1. Pick a meal (Lunch has 193 dishes) and an engine, then tap **Start**.
2. Answer the questions. **Back** undoes the last step; **Just recommend
   something** asks for a proposal right away.
3. When a dish is proposed, accept it or tap **No, something else**.
4. The result shows the dish, the cafeteria and the price.

Without the app, the same engines run in a terminal:

```bash
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU
python backend/manage.py demo_llm_engine --date 2026-09-29 --meal LU     # needs the key
```

### Tests

```bash
python backend/manage.py test menus question_engines recommend     # 183 tests, no API key
cd client && ./gradlew testDebugUnitTest                            # 58 unit tests
cd client && ./gradlew connectedDebugAndroidTest                    # 34 UI tests, needs an emulator
```

## Environment we used

| | |
| --- | --- |
| OS | macOS 26.6 (Apple Silicon) |
| Server | Python 3.14, Django 5.2, SQLite |
| LLM | Gemini (`gemini-3.5-flash-lite` for questions) through `langchain-google-genai` 4.4 |
| Android build | Android Studio 2026.1, Gradle 8.13, Android Gradle Plugin 8.12, Kotlin 2.0.21, JDK 21 |
| Android target | `compileSdk` 36, `minSdk` 26 |
| Devices | Emulator "Medium Phone" (API 36) and a Galaxy Note20 (SM-N981N) over USB |

## What the demo demonstrates

### Features implemented

- **Cafeteria menu database.** A day's SNU cafeteria menu is fetched, cleaned
  and stored, and each dish is tagged with food features by an LLM. The shared
  snapshot holds the result for one day.
- **Decision-tree question engine.** Picks the next question from the dishes'
  features, updates its belief after each answer, and proposes a dish or a kind
  of dish. Runs without any API key.
- **LLM question engine.** Gemini writes each question from the dish names
  alone and proposes a dish. If a call fails or times out, the session goes on
  with a fixed question or a random dish.
- **REST session API.** One API runs either engine: start a session, answer,
  accept or reject a proposal, ask for a recommendation now, and undo.
- **Android app.** One screen that follows the session: start, question,
  proposal, result. The start screen chooses the meal and the engine.

### Goals of the prototype

- Show the whole path working end to end: menu data → question engine → REST
  API → phone.
- Check that a short series of yes/no questions can lead to a real dish on
  today's menu, with a way out at every step (undo, recommend now, reject).
- Put the two engines behind one interface so they can be compared on the same
  menu in the same app.

### Known limits

- Only the 2026-09-29 menu is included. Other dates need a menu fetch and a
  Gemini key for tagging.
- Sessions live in server memory; restarting the server ends them.
- The API has no login. It is meant for a local demo, not a public server.
- We have not yet measured how often people accept the first proposal.

## More detail

- [Android client and REST contract](client/README.md)
- [Menu database and feature extraction](backend/README.md)
- [Decision-tree engine](backend/question_engines/decision_tree/README.md)
- [LLM engine](backend/question_engines/llm/README.md)
- [Requirements and design Wiki](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki)
