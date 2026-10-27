# Agent workflow

Codex and Claude share `AGENTS.md` and the commands below. Use Python 3.11+;
only direct Google Sheets access needs optional dependencies. Run from the
repository root or use the absolute script path. `--help` describes each command;
all command output is JSON for either agent to consume.

## Work records

```bash
python tools/harness.py task i3-P3 --owner "Your name" --title "Project harness"
python tools/harness.py task
python tools/harness.py task --kind decision --note "What changed and why" --ref "PR, commit or session"
python tools/harness.py task
python tools/harness.py task --set wiki_state=prepared --set "wiki_owner=Your name"
```

Records in `.harness/` connect the task, contributor, branch, sources and evidence.
Starting an existing task resumes it. Use `task i3-P3` to select/resume a task;
`usage` and `sheet` accept `--task i3-P3` and otherwise use the active task. Use separate
worktrees for concurrent agents: task records have one writer. The contributor
is not necessarily the schedule assignee; coordinate before entering shared totals.

Use `task --set FIELD=VALUE` for confirmed values; `task --help` lists field names and formats.
Implementation, opening a PR and reviewing it are distinct work items. Do not infer
human hours from conversation timestamps or mark a task complete before its work
is done. Use Git and `gh` directly to inspect changes, commits and PRs.

## Session usage and prompts

```bash
python tools/harness.py usage --tool codex --file /path/to/session.jsonl \
  --since 2026-10-27T13:00:00+09:00 --until 2026-10-27T14:00:00+09:00
python tools/harness.py usage
python tools/harness.py bundle 3
```

Use `--tool claude` for Claude Code. Intervals include the start and exclude the
end; defaults are task creation and attachment time. Reattach to extend an interval.
Collection recomputes totals and rejects attribution overlapping another local task.
Attach child sessions explicitly; do not charge both aggregate and child usage.

Find logs on the machine that ran the agent: Codex uses `$CODEX_HOME/sessions`
(default `~/.codex/sessions`); Claude uses `$CLAUDE_CONFIG_DIR/projects` (default
`~/.claude/projects`). The exporter dry-run helps select a repository/date range.
Confirm session IDs, recorded `cwd` and event timestamps against the task; a filename
alone does not prove attribution. Check child logs separately. For interleaved A/B/A
work, attach A's two intervals separately, e.g. 13:00–13:20 and 14:00–14:30, omitting B.

Codex prefers per-response usage records, deduplicated by response ID. Older logs
use cumulative-counter differences and the first last-call usage, excluding inherited
totals. Cache reads and reasoning are already included. Claude
adds uncached input, cache reads, cache creation and output once per request/message.
Malformed records or counter resets produce warnings and hold tokens out of sheet
updates. Missing measurements stay missing. These totals are not billing estimates.
Recorded time unions Codex turn intervals, including tool waits and aborted turns,
clipped to the assigned ranges. Open turns run provisionally to the cutoff; overlapping
agents count once and gaps between turns are excluded. Divide seconds by 3600 for
this wall-time convention; record the cutoff and method with the hours. Claude time
is not measured. Running sessions need recollection after their final usage is saved.

The private iteration bundle contains task evidence and unredacted input-prompt
candidates. Review originals for missing prompts, generated wrappers and attachments.
It covers only local attached sources, not the whole team. Use the
[course exporter](https://github.com/snuhcs-course/session-exporter) for each member's
history: dry-run, inspect selections/exclusions, review redaction, then export.
Check names/student IDs with `--redact-term`; outside-repo and remote sessions may
be missing. Preserve original records and never upload the private bundle directly.

## Schedule access

Copy `.env.harness.example` to `.env.harness` and set only `METCHU_SCHEDULE_URL`.
Keep the URL's `gid` when available. The local config, records and credentials are
ignored by Git; application `.env` is not loaded.

Agents with authenticated Sheets tools can use them directly: read metadata and
headers, locate one `Iter`/`ID` row, check its assignee, reread before writing,
preserve formulas and unrelated fields, and verify readback. No snapshot conversion
or shared OAuth token is needed. Each agent environment needs its own connection.

For the same direct CLI in either agent, follow Google's [Desktop OAuth setup](https://developers.google.com/workspace/sheets/api/quickstart/python), enable Sheets API, then:

```bash
python -m pip install -r tools/requirements-sheets.txt
python tools/harness.py sheet --login /private/path/desktop-client.json
python tools/harness.py sheet
python tools/harness.py sheet --apply
```

Login is explicit; tokens stay in `.harness/google-token.json` with restrictive
permissions where supported. Keep the client JSON out of Git too. The script
discovers headers and validates dropdowns, dates and numbers. It updates only
recorded hours, tokens, completion date, status and commit, using absolute values.
Apply rereads the row, checks the saved preview, writes cells and verifies readback.
Repeated application is a no-op. Formula cells are never replaced. Checks and writes
are not an atomic lock: coordinate same-row edits and read back after a timeout.

## PRs and iteration closeout

Use the PR template. Prepare wiki changes during review and publish implemented
behavior after merge against final code. Track pages and follow-up owner in a
`wiki` note; small changes may need no wiki update. The wiki is a separate repository:
follow its instructions, synchronize before editing and preserve concurrent changes.
Publication and other external actions follow existing authorization. Follow-up
runs when the author or next agent resumes, not in a background service.

At iteration close, review all members' interaction histories. Write the English
500–700-word AI report covering use, input prompts, successes, errors, prompt
revisions and actual manual fixes. Link evidence, the verbatim original-language
prompt log and the sidebar entry. Mark privacy redactions; do not present translations
as quotations. Full replies need not be published. Blanket AI-code headers are not
required by v1.1; mark reported manual fixes when useful, and never invent review.

Keep Design and Testing Documentation separate and prepare both iteration PDFs.
Before AI evaluation, commit at least 30 frozen cases and pass thresholds, with
model/prompt/settings/command. Submitted cases may be added, not edited or removed.
Report revision, outcomes and failures; preserve original plans alongside revisions.
Discuss uncertain ground truth with the TA. Fix at least five UAT stories in
Iteration 3, report results in Iteration 4, and conduct alpha before beta in Iteration 5.
Distinguish synthetic and human results. These rules follow the course Design,
Testing, AI Collaboration v1.1 and Session Exporter guidelines; consult newer versions
when supplied. The harness prepares evidence and does not submit to eTL.

## Compatibility and tests

Older Claude Code can use `python tools/harness.py launch claude` to load AGENTS.md
explicitly; `launch codex` starts Codex at the repo root. Check instruction loading
in either CLI or GUI. The launcher does not change permissions or install models.

Run `python -m pytest tools/tests`, `python -m pytest backend`, and `git diff --check`.
Harness tests use synthetic sessions, temporary Git repositories and mocked Sheets;
they do not call paid APIs or change team records. Linux/Windows CI results and live
write access must be verified separately, not inferred from local tests.
