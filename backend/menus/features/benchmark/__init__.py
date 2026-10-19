# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Feature extraction benchmark: experiments that inform design choices.

The unit tests check that the code works; this package measures how good the
extracted mean/std values are, as far as that can be measured.

    build_eval_menu_set         -> menu_set.json  variant / invariant dishes of past days
    collect_feature_runs        -> runs.jsonl     the only step that calls the extraction LLM
    export_feature_rating_form  -> ratings.csv    a blank form for human raters
    benchmark_features          -> report.md, CSVs and histograms (no LLM call)

The report's sections:
  integrity    - 33 keys (32 measured + meal_variety for stored foods), bounds, std² <= mean(1-mean)
  distribution - each feature's histogram of means, and dishes the features cannot tell apart
  stability    - repeated extraction, with the food order or the rubric's feature order shuffled
  human        - LLM means and stds against human ratings, next to how well the raters agree
  triplets     - "anchor is closer to near than to far", by kind (close / distinct) and source
  downstream   - the decision tree with AI vs human features: same policy, same simulated users

Only integrity passes or fails; the rest are numbers to read. Variant dishes (lines
that change from day to day) and invariant dishes (the fixed-menu catalog) are
reported apart in distribution, stability and human (menu_set.py).
"""

HIGH, LOW = 0.7, 0.3  # a mean at or beyond these reads as a clear "has it" / "does not"
