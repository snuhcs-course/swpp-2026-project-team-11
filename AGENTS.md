# AGENTS.md

Rules for AI coding agents in this repository. People start from [README.md](README.md).
When a convention changes, change it here in the same PR.

These instructions are shared by Codex and Claude Code. Older Claude Code versions
can start with `python tools/harness.py launch claude` to load this file explicitly.

## Start and finish a task

- Run `python tools/harness.py task`. Read Git status and preserve unrelated work.
- For a new work item, run `python tools/harness.py task i3-P3 --owner "Your name"`.
  Use the actual iteration and task ID; do not assume the person requesting work is
  the schedule's assignee. A task may span multiple agent sessions.
- Record useful decisions, failures, verification results and pending wiki changes with
  `task --kind <kind> --note <text> --ref <evidence>`. Record milestones, not every action.
- Before a PR, run `task` and collect usage for explicitly attributed session
  intervals. Use `--help` for commands and [the workflow](docs/agent-workflow.md) for
  accounting, sheet access, documentation and iteration closeout.
- Prepare wiki changes with the PR; publish implemented behavior after merge against
  the final code. Keep a named owner for pending documentation. Small changes may
  need no wiki update; explain that in the PR. Do not update the wiki every commit.
- Preview schedule edits with `sheet`; apply verified, authorized
  changes with `sheet --apply`, then check readback. Do not invent hours, tokens,
  human edits or review. Missing data stays missing. Existing authorization carries
  forward; do not ask again for routine work within its scope.
- At iteration close, use `bundle <n>` to collect local evidence. Review
  every contributor's interaction history before writing the team report. The
  bundle alone is neither the report nor proof that all contributors are covered.

Metchu! picks an SNU cafeteria meal by asking yes/no questions. Two question
engines share one session API: MVP1, the decision tree (`backend/question_engines/decision_tree`,
feature-based, no API key), and MVP2, the LLM engine (`backend/question_engines/llm`,
Gemini writes questions from dish names). `backend/recommend` serves them to the
Android app in `client/`.

## Commands

```bash
pytest backend                                   # all backend tests; no key, no network
python -m pytest tools/tests                     # harness tests; synthetic data only
METCHU_MENU_DATE=2026-09-29 python backend/manage.py runserver 0.0.0.0:8000
                                                 # after migrate + loaddata menus_2026-09-29
cd client && ./gradlew testDebugUnitTest         # JDK 21; the build fails on JDK 25
```

## Tests

- Changes come with tests in the relevant package's `tests/` (harness: `tools/tests/`).
  A bug fix gets a test that fails without the fix.
- Run `pytest backend` before you commit, push or report code work as done. If you
  changed `client/`, also run `./gradlew testDebugUnitTest`. For harness changes,
  run the harness tests too. For prose-only changes, check the diff and links;
  application test suites are not needed. Report failures and verification limits.
- Tests need no API key or network: pass a fake LLM (`question_engines/llm/tests/helpers.py`,
  `FakeLLM` in `menus/tests/test_extract_features.py`) and patch `menus.sources.siksha.fetch_raw`.

## Contracts that break silently

- **One engine interface**: `start / answer / feedback / recommend_now / undo / snapshot /
  from_snapshot / diagnostics`, the step types `question / guess / recommendation /
  unavailable`, and the answer IDs in `decision_tree/contracts.py`. `recommend/` and
  the client depend on it: change both engines, the API and the client together.
- **REST JSON**: when a reply changes, update the client models and recapture
  `client/app/src/sharedTest/resources/contract/*.json` from the real server.
- **Feature schema** (`menus/features/schema.py`): a change to keys, questions or
  meaning bumps `FEATURE_VERSION`, which re-tags every food.
- **Menu preprocessing prompt** (`menus/preprocess/prompt.py`): a change bumps
  `PREPROCESS_VERSION` and updates `PROMPT_SHA256` (`menus/preprocess/mapper.py`; a test
  checks the pair), so cached `MenuLine` answers are resolved again.
- **Snapshots**: if what a saved session means changes, bump `POLICY_VERSION`
  (`decision_tree/planning.py`) or `ENGINE_VERSION` (`llm/engine.py`).
- **Shared data**: rebuild `menus/fixtures/menus_2026-09-29.json` only as backend/README.md,
  "Making a new shared snapshot", describes. Files a person reviewed (the P7
  preprocessing catalog and overrides) are corrected by people, never regenerated.
- `decision_tree/` stays pure Python + numpy: no ORM, HTTP or LLM imports.

## Ask before you

- Call Gemini or another paid API for real (`extract_features`, `demo_llm_engine`,
  LLM sessions on a server with a key, menu preprocessing). Say how many calls first;
  use `--dry-run` where it exists.
- Write to the shared database (`DATABASE_URL` pointing at the team's Supabase).
- Push, open or merge a PR, tag, or delete branches.
- Expose the server publicly (a tunnel).

## Secrets

- The team's keys are GitHub Actions repository secrets, named as in `.env`:
  `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DATABASE_URL`. Workflows read
  them as `${{ secrets.NAME }}` and stop with a clear error when one is missing. Settings
  that are not secret, such as `METCHU_MENU_MODEL`, are repository variables (`${{ vars.NAME }}`).
- A new key goes, commented out, into `.env.example`; a repository admin adds the secret.
- Never print, log or commit a key, locally (`.env`) or anywhere else.

## Gotchas

- `manage.py` loads the repo-root `.env`; pytest does not. With a key in `.env`,
  `manage.py` commands and `runserver` call Gemini for real.
- The shared snapshot only has 2026-09-29; without `METCHU_MENU_DATE` the server
  looks for today's menu and sessions have no candidates.
- Leave the temperature of Gemini 3 models unset (Google's default).

## Code

- Keep code clean and concise: the simplest change that works, no dead code, no
  speculative options or abstractions, no comments that restate the code.
- English for code, docs, commits and PRs. App UI text and engine questions are
  English; dish and cafeteria names stay Korean. Commands under `menus/` print Korean.
- Follow AI Collaboration Report Guidelines v1.1: blanket AI-generated headers are
  not required. For a manual fix discussed in the report, add a nearby marker only
  when useful for locating it. Claim human review only when it actually happened.
- Update the README section that describes what you changed in the same change.

## Git conventions

People often commit and push themselves. Commit or push only when asked; when you
do, or draft messages for someone, use these formats.

- **Branches** start from `MVP`, and PRs target `MVP`: `feat/i<iteration>-p<n>-<topic>` for a
  work item of the schedule sheet, `feat/i<iteration>-a<n>-<topic>` for work added during the
  iteration. Iteration ends are tagged `iteration-<n>` on `MVP`.
  A dependent PR may start from and temporarily target its prerequisite branch
  to keep the review diff separate. Name that dependency in the PR body; after
  it merges, retarget the dependent PR to `MVP` before merging it.
- **Commits**: `type(i<iteration>-P<n>): subject` (`i<iteration>-A<n>` for added work); types `feat`,
  `fix`, `test`, `docs`, `ci`, `chore`, `refactor`. Lower-case imperative subject,
  at most about 70 characters; an optional body of one to three lines on why; no AI
  co-author trailer. Tests in their own `test(...)` commit, docs in one `docs(...)`
  commit per batch.
- **PRs**: use [.github/pull_request_template.md](.github/pull_request_template.md).
  Include the work items, implementation, validation and wiki follow-up owner.

## Evaluation and reporting

- Before AI evaluation, commit at least 30 frozen cases and the pass thresholds.
  Record model, prompt version, settings and command. Do not set thresholds after
  seeing results or silently rewrite submitted cases and plans.
- Keep at least five UAT user stories fixed from Iteration 3. Put test plans and
  results in Testing Documentation, separately from Design Documentation.
- Report prose is English. Input prompts remain verbatim in their original language,
  with explicit privacy redactions. Never label translations as verbatim prompts.
- Review session exports privately before sharing. Full transcripts need not be
  published on the wiki. Follow the v1.1 report and exporter procedures in the workflow.
