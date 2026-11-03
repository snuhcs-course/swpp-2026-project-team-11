# Updating the mini PC from Codex on iPhone

The live Metchu API runs on the Windows mini PC, not the development Mac.
Open the paired mini-PC host in ChatGPT/Codex on iPhone and use
`%LOCALAPPDATA%\MetchuHost` as the project folder.

The installation has:

- `release.txt`: the source commit loaded by the host and the daily-menu job;
- `releases/<commit>/backend`: an immutable copy of that commit's backend;
- `venv/Scripts/python.exe`: the installed backend environment;
- `private/menu.sqlite3`: the authoritative application database;
- `Task.ps1`: start, stop, restart and inspect the host;
- the Windows tasks `Metchu-Host` (at boot) and `Metchu-DailyMenus` (KST daily refresh).

The ngrok address is fixed in private host configuration. Read it with
`./Task.ps1 -Action status`; credentials stay in `private/`.
The old Supabase daily GitHub Actions workflow was disabled at cutover.

## Apply a merged backend change

Ask the phone's Codex to perform this checklist on the mini PC:

1. Fetch the merged `main` revision from the team repository and stage its
   `backend/` under a new `releases/<full commit>/backend` directory. Keep the
   previous revision in `release.txt` for rollback. Public source can be downloaded
   from `https://github.com/snuhcs-course/swpp-2026-project-team-11/archive/<commit>.zip`.
2. Compare `backend/requirements.txt` with the active release and run the backend
   suite with the installed interpreter, from the staged release:
   `& "$env:LOCALAPPDATA\MetchuHost\venv\Scripts\python.exe" -m pytest backend`.
   Tests use their own SQLite database and fake model providers.
3. Disable new `Metchu-DailyMenus` starts and wait for an active update to finish.
   Stop `Metchu-Host` with `./Task.ps1 -Action stop`, then use SQLite's backup API
   to create a dated backup of `private/menu.sqlite3`.
4. Switch `release.txt` to the verified full commit and start the host with
   `./Task.ps1 -Action start`. This RMS menu change needs no schema migration,
   model training or retagging: it composes the existing component vectors when
   creating a new recommendation session.
   The installed `daily_menus.py` also lives outside the release. For this cleanup,
   remove its assignment adding ` (세트)` to `Food.display_name` and remove
   `display_name` from that assignment's save-field list. It should preserve the
   stored component label just like `extract_features`. Verify it with
   `venv/Scripts/python.exe -m py_compile daily_menus.py`; no data backfill is needed.
5. Check `/api/health/` locally and through the fixed ngrok address. Create
   separate DT and RL sessions for a known menu date, request a proposal, reject
   it and undo. Confirm a set is named with its exact sales-menu text and that
   rejection does not offer another component of that same set.
6. Re-enable the daily-menu task. On a failed check, stop the host, restore the
   previous release pointer and restart it before re-enabling updates.

Stop/start drops active in-memory dialogues. New sessions use the new source;
a cached APK can display the original names with the existing JSON shape.
The numerical `food_id` field is now an opaque sales-menu candidate ID, so
consumers must not use it to query the internal `menus_food` table.
Use `get_catalog` or `export_candidates` to inspect current recommendation inputs.

No deployment from the Mac was performed for this change: the mini PC's LAN
SSH address was unreachable after the network changed. The operator must verify
the final merged revision on the host as above.
