# Metchu! — Iteration 1 Demo (SNU SWPP 2026 Team 11)

Metchu helps you decide what to eat at the SNU cafeterias. It asks a few quick
questions and proposes a dish from that day's menu. This branch is the working
prototype at the end of Iteration 1.

## Demo video

[Watch the demo video](docs/iteration-1-demo.mp4) (2 min 18 s, a screen recording
of the app).

It plays two sessions on the same lunch menu (September 29, 2026, 193 dishes),
one with each question engine:

1. **Decision tree** (0:00). The app asks yes/no questions about the food. When
   it proposes a kind of dish (볶음밥, then 정식/뷔페) the user says no, and it
   goes on to propose a single dish, 숯불양념치킨덮밥, which the user accepts. The
   result shows the cafeteria and the price.
2. **LLM** (from about 1:15). Gemini writes the questions. The user rejects its first
   proposal, 마라쌀국수, answers a few more questions, and gets 우삼겹짬뽕.

[Step 4](#4-try-it) below repeats these two sessions on your own machine.

## How to run the demo

The demo has two parts: a Django server that runs the question engines, and an
Android app that plays a session against it. Both run on one machine; the app
runs on an Android emulator.

You need:

- Python 3.11 or newer
- Android Studio with an emulator (we used "Medium Phone", API 36)
- Only for the LLM half of the demo: a free Gemini API key

### 1. Start the server

From the repository root:

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

Leave this terminal open. To check the server from a second terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/ -H 'Content-Type: application/json' -d '{"meal": "LU"}'
```

It answers with a JSON session whose `candidate_count` is 193 and whose first
`step` is a question.

### 2. (Optional) Enable the LLM engine

The decision-tree engine needs nothing else. To try the LLM engine as well, get
a key from [Google AI Studio](https://aistudio.google.com/apikey) and put it in
a `.env` file in the repository root **before** starting the server:

```bash
cp .env.example .env      # then set GOOGLE_API_KEY=your-key
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

### 4. Try it

This is the flow in the video.

1. On the start screen, keep **Lunch** and **Decision tree**, and tap **Start**.
   The top line shows `2026-09-29 · LUNCH · 193 DISHES · DECISION TREE`.
2. Answer the questions with any of the six buttons. **Back** undoes the last
   step. There is no fixed number of questions: the engine proposes something
   when it is confident enough, and **Just recommend something** asks for a
   proposal right away.
3. A proposal is either one dish or a kind of dish with an example. Tap
   **No, something else** to keep going, or **Yes, I'll have this** to accept.
4. The result shows the dish, the cafeteria and the price. Tap **Start over**.
5. Choose **LLM** and tap **Start** to play the same menu with Gemini writing
   the questions (needs the key from step 2). Each step takes a few seconds.

Your questions and dishes will differ from the video's: they depend on your
answers, and the LLM engine words its questions differently every time.

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
