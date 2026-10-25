# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Question engine benchmark: decision tree (MVP1) vs LLM engine (MVP2).

    build_engine_scenarios  -> scenarios.json   wanted menus + frozen candidate lists
    collect_engine_sessions -> sessions.jsonl   simulated users play both engines (LLM calls)
    play_engine_session     -> human sessions   a person plays, engine hidden (user study)
    validate_simulator      -> simulator check  the simulated user, asked what people were asked
    benchmark_engines       -> report.md        the sections below (no LLM call)
    run_engine_benchmark    -> all of it in engine_benchmark_results/NAME/

The main metrics, per situation and engine: questions per session, first-pick
acceptance rate, latency per session and cost per session. First pick is set against
baselines: proposing without a question, a random dish, and the other engine.

Situations (scenarios.py): the wanted menu is served, several served menus would
do, it is not served, or it is served next to a close alternative that no question
tells apart. Each scenario also has a certainty level: how often the user answers
vaguely or wrongly (simulator.py). The simulated user answers from the wanted
menu's name alone, so the decision tree is also tested against features that were
extracted wrongly. Both engines face the same scenarios and the same answers.

A proposal is accepted when it is the wanted menu or a kind of it: wanting 볶음밥,
소고기볶음밥 is fine; wanting 닭고기볶음밥, it is not. When the wanted menu is not
served, the simulated user decides whether a proposal would do.
"""

SITUATIONS = ("in_menu", "multiple", "not_in_menu", "close_alternative")
COUNTS = {"in_menu": 40, "multiple": 20, "not_in_menu": 20, "close_alternative": 20}
CERTAINTY = ("high", "medium", "low")
ENGINES = ("decision_tree", "llm")
