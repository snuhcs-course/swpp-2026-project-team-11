# Original menu profiles

This builds on merged #31 and #34. Both catalogue readers
return `(candidates, schema)`. The REST candidate fields remain unchanged.

## Recommendation unit and identity

A candidate is one purchasable menu with its full price and restaurant offers.
Source price suffixes and notices are removed from the title; the dish/set title
is preserved. Internal main dishes are not separate proposals of that same set.

Catalogue readers never allocate IDs or modify the DB. `fetch_menus`,
`import_stores`, ordinary source-record saves and fixture loading prepare recipe
IDs while writing. After upgrading an existing DB, run `register_menu_ids` once;
unprepared recipes are logged and withheld. Raw SQL/bulk source edits must also
call this explicit registration step.

`food_id` now refers to the durable `menus_salesmenu` registry, not `menus_food`,
`menus_menuitem` or `menus_storemenu`. Replacing source rows or changing a price,
date or meal does not change the ID for an unchanged recipe. Source namespaces
prevent cafeteria/general collisions.

Imported profiles distinguish source, restaurant code, title and normalized
source description. Equal titles with different sizes/compositions stay separate.
A changed recipe/description needs a new annotation and has a separate identity;
an unmatched change is withheld rather than silently using the old profile.
Without an annotation, equal title/description/main-name/set-status recipes can
share offers. Switching from computed to restaurant-specific annotations introduces
new IDs. Consumers must not carry IDs from an older deployment or a different
database into the imported catalogue. Current session feedback uses the IDs
returned by that session; this does not define permanent preference semantics.

Equivalent menus (same cleaned title, full mean/std vectors, composition and
explicit portion markers) share one candidate with all eligible restaurant/price
offers. Unknown compositions require matching descriptions. Different components
or portions remain separate even if vectors collide. A merged candidate uses the
lowest active member ID; changes in group membership may change that transport
ID. Rejecting the candidate therefore rejects its duplicate offers together.

## External data import

Keep crawl snapshots, annotations, exports and checkpoints in `.local/menus/`
or outside the checkout. That directory and common root-level export names are
ignored by Git. This PR contains no collected/generated dataset or weights.

The input is a JSON array. Each record has `store_code`, `name`, the original
`description` (empty if absent), `features` and `feature_std` dictionaries covering
the current 33 keys. Optional `model`, `reasoning_effort`, `annotation_version`,
`std_source`, `interpreted_description`, `source_corrected` and `components` fields
are retained as provenance. Feature means and recipe-spread proxies must be kept
distinct from human measurements. The import makes no model calls.

```sh
python backend/manage.py register_menu_ids
python backend/manage.py import_menu_features --file .local/menus/menu_features.json --dry-run
python backend/manage.py import_menu_features --file .local/menus/menu_features.json
```

Use `--source cafeteria` for cafeteria records. Source descriptions must match the
captured source rows; the current cafeteria adapter supplies an empty description.
An interpreted description belongs in metadata and must not replace that source
fingerprint. Supporting richer cafeteria source descriptions is an adapter follow-up.

Validation completes before the atomic write. Conflicting duplicate records fail
without partial writes. Reimporting the same profile preserves its registry ID.
Whole-line allergen filtering still runs before profiles reach an engine. A profile
does not certify allergen safety or override missing allergen tags.

When no imported profile exists, complete current-version main vectors are
combined feature by feature with `sqrt(sum(x_i**2)/n)`; one main passes through.
The std composition is an RMS proxy, not a measured distribution. An invalid or
partially tagged menu is withheld without breaking unrelated menus.

## Deployment handoff

Pause the API and daily writer, back up the active database and apply migrations
through `menus.0007` with the staged release before starting either process.
Migration 0006 belongs to #34 and removes `Food.display_name`; external writers
must no longer assign/save that field. Run `register_menu_ids`, then import the external profiles on the host
against that same database, then check health and DT/RL propose/reject/undo.

The mini PC's installed daily writer is outside this repository. Its owner must
connect source/description updates to this same import/catalogue contract and
include #30's fixed boards. This PR does not deploy or replace that job, alter the
GitHub scheduler, or retrain the RL policy. Follow-up owner: Mingyu Lee.

Groups remain supported by pure-engine callers and older API contracts. Live
actual-menu catalogues disable them; retaining the client decoder avoids coupling
this backend change to an Android compatibility cleanup.
