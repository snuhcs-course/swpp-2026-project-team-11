# Metchu! — SNU SWPP 2026 Team 11

Metchu helps users discover what they feel like eating through adaptive
questions. The current backend contains the cafeteria-menu DB and the P10
feature-based question engine. The LLM conversation engine, shared P17
interface/REST layer, and Android integration are separate iteration tasks.

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

```bash
python backend/manage.py test menus question_engines.decision_tree
python backend/manage.py benchmark_decision_tree --date 2026-09-29 --meal LU --trials 24 --output /tmp/benchmark.json
```

## Component guides

- [Cafeteria DB setup and feature extraction](backend/README.md)
- [P10 engine API, output shapes, snapshots, and P17/P19/P20 handoff](backend/question_engines/decision_tree/README.md)
- [Recorded paired synthetic benchmark](backend/question_engines/decision_tree/benchmarks/cafeteria_20260929_lunch.json)
- [Requirements and design Wiki](https://github.com/snuhcs-course/swpp-2026-project-team-11/wiki)

Food and cafeteria names retain their source language. Authored engine prompts,
answer labels, comments, documentation, commits and PR content are English.
The benchmark reports synthetic menu matching and computation time; it does
not establish human first-pick acceptance or handset inference performance.
