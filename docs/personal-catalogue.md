# Personal recommendation catalogue (i4-P19)

All engines and daily ingestion use **v3: 53 features**. The current meanings and
English/Korean question texts live in `backend/question_engines/feature_schema.json`.
`menus/features/instructions.txt` is the user-authored rubric used for the reviewed
canonical dishes. The API changes only its CSV transport envelope to structured
JSON. `mean` is sensory intensity, `std` is common recipe variation, and `mask`
is knowledge availability. Unknown values persist as paired JSON nulls, never as
known zero. The decision tree makes their directional evidence neutral.

The retired v20 weights and 33-feature serving schema are removed. Prior deployment
code and the DB were backed up privately on the mini PC before this work. Historic
benchmark reports remain historic evidence; they are not v3 training or evaluation.

## Candidate pool

General restaurant sales menus resolve through imported DB mappings to the
267 reviewed canonical dishes. The input has 7,698 sales rows: 7,475 map to active
dishes, and 223 resolve to null (200 original nulls plus 23 rows targeting dropped
덮밥, 두부요리, 콘치즈 or 국). Unknown or ambiguous new menu names are excluded until
the mapping is reviewed; the model never guesses their category.

The operational CSV is not tracked or opened by the service. Import it once with
`import_canonical_mapping --file <operator-file>` (preview), then the same command
with `--apply` against the staged deployment DB. This transaction replaces the
old general SalesMenu recipe/profile records with current mapping records in the
same table; it does not touch source menus, prices or allergens. The source hash
is retained on the records. No additional mapping table or runtime CSV fallback
is introduced. `run_store_pipeline --mapping <operator-file>` re-imports it after
each crawl; unmatched recipes remain excluded. The existing campus preprocessing cache is still needed to
understand complete menus and allergens.

Import matching is exact restaurant-name/raw-menu-name first. A unique formatting-only
fallback removes square-bracket annotations, spaces and underscores. This resolves
37 spelling differences in the operational import. Exact lookup is essential:
stripping first can collapse conflicting source entries. At serving time lookup uses the stable restaurant-code/menu/description key.
Branch identity remains in `restaurant_code` and coordinates on every actual offer.

A canonical type enters once when at least one offer survives meal, allergy and
location filtering. More restaurants/variants do not multiply its neural prior.
Offers retain `menu_name`, `restaurant_code`, original price and coordinates, so
results and the restaurant-menu sheet can show what is actually sold. Offer-level
allergen tags are independent of sensory features. Group recommendation also
filters each member's returned sales offers, including two variants of one type
at the same restaurant with different allergens.

Canonical candidate IDs reserve `1,000,000,000 + original food_NNN index`.
Campus candidates retain durable SalesMenu IDs. Food IDs are opaque recommendation
IDs, not a foreign key into Food. Do not renumber the surviving canonical IDs.

Campus menus bypass category mapping. `extract_menu_features --date YYYY-MM-DD`
annotates a whole purchasable menu with its component names as context and caches
it by counter, title, meal, composition and exact prompt hash. Price/date changes
reuse a profile; different lunch/dinner recipes with one title do not. Features
and allergens are separate: an unresolved feature profile or allergen result is
withheld as a complete offer by the installed daily writer.

Both sources compete in one 53-feature pool. DT and group rooms use that same
schema and translated question definitions; **group mode remains DT-only**.

## Frozen personal model

- Model: `personal.53.1`, 562,123 parameters.
- Chosen checkpoint: PPO iteration 42,759, highest recorded training-window score
  when selected for this PR. It is fixed, not a moving best-model pointer.
- Monitoring-window score: -11.8749627266. This is a synthetic training score,
  not measured human satisfaction or an independent validation result.
- The checked-in NPZ contains only weights and the canonical acceptance priors;
  `assets/manifest.json` identifies the source checkpoint and SHA-256 checksums.
- The model runs in PyTorch on **CPU**. A shared encoder handles variable candidate
  counts and the current 53 mean/std/mask values; no food-ID embedding is present.
- Canonical priors come from the training population. An unseen campus menu retains
  its own identity/features and gets a smooth prior from the eight nearest known
  sensory profiles (`exp(-8 * mean absolute difference)`, jointly known axes).
  This prior transfer is an explicit serving assumption; calibration on actual
  campus choices is not established by the synthetic training score.
- Questions use softmax of DT value plus the learned correction. PPO controls
  question selection and proposal timing. Food selection is acceptance argmax.
- After **20 answered questions/proposal decisions in total**, serving switches
  to proposal-only mode. Rejections remove candidates; it proposes the next best
  until acceptance or exhaustion. There is no forced failure at request 20.
- Undo and snapshots retain the selected question, proposal, rejections and RNG.
  A one-candidate pool can propose immediately because there is no choice to elicit.

The serving runtime contains no simulator, training optimizer or CUDA call.
CPU-only uv package sources follow the [official PyTorch integration guide](https://docs.astral.sh/uv/guides/integration/pytorch/).

## Verification and fixtures

Run `uv run --isolated --locked python -m pytest backend`. Android JVM checks use
JDK 21 and `client/gradlew testDebugUnitTest`. The new integration tests cover
canonical deduplication, original offer names, dropped/unknown mappings, masks,
whole-menu cache invalidation, source competition, prior independence from offer
counts, snapshot/undo, 20-plus rejections and Korean/English group questions.

`menus_v3_contract.json` is a **synthetic, partial test fixture**: shared numeric
axes from the old snapshot remain test values and newly introduced axes are null.
It exercises schema/transport behavior and is never an operational retagging
result. The original shared snapshot and human-reviewed source data are unchanged.
Do not relabel old DB values as v3; run the new extraction workflow.

See [the mini-PC migration runbook](mini-pc-host.md) for post-merge installation.
