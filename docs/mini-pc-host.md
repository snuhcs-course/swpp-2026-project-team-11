# Mini-PC deployment and rollback

The active checkout is the mini PC's server clone.
Runtime scripts, logs, private data and SQLite are in `.local/hosting` below it.
The old `%LOCALAPPDATA%\MetchuHost` entry points forward to this checkout; its
release pointer and recovery DB are not current. Secrets remain in the checkout's
ignored `.env`. Do not print them or copy them into a PR.

## After this PR merges

The PR does not install itself or restart the live service.

1. Inspect the actual checkout, process commands, daily-task state and DB before
   changing anything. Pause new daily starts and wait for any current writer.
   Keep a private, integrity-checked SQLite backup and source/runtime archives.
   A pre-P19 rollback bundle already exists in
   `.local/hosting/private/backups/pre-p19-53-20261117-222126`.
2. Fetch and fast-forward to the merged main. Inspect the merged diff, including
   any intervening group PRs; do not replace unrelated local runtime configuration.
3. Verify the uv executable and the physical versioned Python executable. The
   current `.venv` launcher has reproduced an SSH junction error. Use uv's locked,
   isolated environment and the physical Python path, as `tools/hosting/Run.ps1`
   does, instead of reusing that launcher. Prewarm this environment before stopping
   the API; no application or model API call is needed to import the modules.
4. Run the backend suite through `uv run --isolated --locked python -m pytest backend`.
   Stop the host using `.local/hosting/Host.ps1 -Action stop`. This drops in-memory
   solo/group conversations; account and auth tables remain in SQLite.
5. Keep local `api.py` and the existing public URL/private settings. Change the host
   compatibility launcher to `tools/hosting/Run.ps1 -Mode host`; the existing
   supervisor then starts its API child with the same uv-managed interpreter. Change the daily-task
   compatibility launcher to `tools/hosting/Run.ps1 -Mode daily`. Both use the same
   checkout, authoritative DB and uv lock. Do not start a second supervisor or
   bypass the existing writer/singleton locks. Test the actual task account too.
6. Copy the operator-supplied mapping file into private deployment storage; do
   not commit it. On a staged copy of the DB, preview and apply
   `import_canonical_mapping --file <private-file> --apply`. This replaces the
   old general profiles and requires no model calls. Keep the original source
   file for later crawl updates.

   On a staged copy of the private DB, preview `reset_features`; with the verified
   backup retained, run `reset_features --apply` against that staged DB. It removes
   obsolete feature values/versions while preserving Food, SalesMenu identities
   and allergen tags. There is no parallel 33-feature serving path.
7. Run the new daily writer on the staged DB through the preserved host root and
   budget configuration. It fetches today's menus and extracts whole-menu v3
   profiles, allergens and labels. The first feature refresh needs paid calls:
   approximately one batch per eight uncached menu descriptions, plus retries;
   determine the actual pending count and current authorization before sending.
   Source/extraction failures must not erase the live catalogue.
8. The daily writer stages and publishes via `tools/hosting/menu_publish.py`,
   updating only `menus_*` tables transactionally. Preserve account/token tables,
   including writes that occurred while tagging ran. Run integrity and foreign-key
   checks before publication. Never replace an open live SQLite file.
9. Start the existing host supervisor, check local/public health and personal DT/RL
   sessions against today's campus plus mapped restaurants. Verify both languages,
   actual sales names/prices, allergy/area filters, category rejection/undo,
   20-plus proposal-only continuation, group DT and new bilingual questions.
   Then re-enable the existing 07:00/09:00/12:00/16:00 daily schedule.

The checked-in daily runner accepts `--root` for an isolated copied host root; its
`.env` settings are loaded from the checkout, but it always uses the private SQLite
inside that root. Do not point it at a teammate's or shared Supabase DB.

## Rollback

Stop only the owned host and writers. Restore the backed-up code/runtime together
with a compatible DB; never feed v3 state to v20 or restore the whole DB over new
account writes without reconciling them. Keep the new failure evidence. Rollback
is an operator action, not an automatic concurrent DB copy.

## Known host concern

The current DB retains operating-hours fields, but main's catalogue loader does
not apply them. This PR preserves the current area/meal/allergy filtering;
restoring the old host-only operating-hours behavior is separate work. Do not
claim that every listed restaurant is open now solely from these fields.

Interaction logs are private (`.local/hosting/private/interaction-logs`), contain
user-provided allergies (version 1 lines, before i5-A1, also the location), and expire after 30 days. Do not publish logs,
DB backups, `.env`, tokens or model-provider credentials.
