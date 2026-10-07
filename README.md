# Metchu! — SNU SWPP 2026 Team 11

Metchu helps users discover what they feel like eating through adaptive
questions. The backend contains the cafeteria-menu DB, two question engines
with the same session API — the P10 feature-based engine (MVP1) and the P13/P14
LLM engine (MVP2) — and a REST API that runs them for the Android client in
`client/`.

## Run the current engine demo

Requires Python 3.11 or newer. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-09-29
python backend/manage.py demo_decision_tree --date 2026-09-29 --meal LU
```

Windows activation: `.venv\Scripts\Activate.ps1`. The fixture contains September
29 only; another date may have no candidates. The question-engine demo uses
the shared fixture and requires no API key. Add `--smoke` for a noninteractive
answer/reject/accept flow, or `--policy lookahead` for the experimental bounded
planner. The default is the greedy information-gain policy.

The LLM engine has the same demo flow and needs `GOOGLE_API_KEY` in the
repo-root `.env` (see the [DB setup guide](backend/README.md#1-put-your-key-in-env)):

```bash
python backend/manage.py demo_llm_engine --date 2026-09-29 --meal LU
```

```bash
python backend/manage.py test menus question_engines
python backend/manage.py benchmark_decision_tree --date 2026-09-29 --meal LU --trials 24 --output /tmp/benchmark.json
```

## Run the Android MVP

The app talks to the Django server over HTTP. Start the server with the fixture
date, then run the `client/` project from Android Studio on an emulator:

```bash
python backend/manage.py migrate
python backend/manage.py loaddata menus_2026-09-29
METCHU_MENU_DATE=2026-09-29 python backend/manage.py runserver 0.0.0.0:8000
```

See the [Android client guide](client/README.md) for the screens, the REST
contract and how to run on a physical phone.

## Component guides

- [Android client and recommendation REST API](client/README.md)

- [Cafeteria DB setup and feature extraction](backend/README.md)
- [P10 engine API, output shapes, snapshots, and P17/P19/P20 handoff](backend/question_engines/decision_tree/README.md)
- [P13/P14 LLM engine API, configuration, failure handling and P17 integration](backend/question_engines/llm/README.md)
- [Recorded paired synthetic benchmark](backend/question_engines/decision_tree/benchmarks/cafeteria_20260929_lunch.json)
- [Requirements and design Wiki](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki)

Food and cafeteria names retain their source language. Authored engine prompts,
answer labels, comments, documentation, commits and PR content are English.
The benchmark reports synthetic menu matching and computation time; it does
not establish human first-pick acceptance or handset inference performance.
