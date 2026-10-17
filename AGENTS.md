# AGENTS.md

Rules for AI coding agents in this repository. People start from [README.md](README.md).
When a convention changes, change it here in the same PR.

Metchu! picks an SNU cafeteria meal by asking yes/no questions. Two question
engines share one session API: MVP1, the decision tree (`backend/question_engines/decision_tree`,
feature-based, no API key), and MVP2, the LLM engine (`backend/question_engines/llm`,
Gemini writes questions from dish names). `backend/recommend` serves them to the
Android app in `client/`.

## Commands

```bash
pytest backend                                   # all backend tests; no key, no network
METCHU_MENU_DATE=2026-09-29 python backend/manage.py runserver 0.0.0.0:8000
                                                 # after migrate + loaddata menus_2026-09-29
cd client && ./gradlew testDebugUnitTest         # JDK 21; the build fails on JDK 25
```

## Tests

- Everything you implement comes with pytest tests in that package's `tests/`. A bug
  fix gets a test that fails without the fix.
- Run `pytest backend` before you commit, push or report work as done, and go ahead
  only when it passes. If you changed `client/`, also run `./gradlew testDebugUnitTest`.
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
  `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `DATABASE_URL`. Workflows read them as
  `${{ secrets.NAME }}` and stop with a clear error when one is missing.
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
- A new file starts with `# AI-generated: written with <tool> (<company>) and reviewed by the team.`
  (`//` in Kotlin).
- Update the README section that describes what you changed in the same change.

## Git conventions

People often commit and push themselves. Commit or push only when asked; when you
do, or draft messages for someone, use these formats.

- **Branches** start from `MVP`, and PRs target `MVP`: `feat/i2-p<n>-<topic>` for a
  work item of the schedule sheet, `feat/i2-a<n>-<topic>` for work added during the
  iteration. Iteration ends are tagged `iteration-<n>` on `MVP`.
- **Commits**: `type(i2-P<n>): subject` (`i2-A<n>` for added work); types `feat`,
  `fix`, `test`, `docs`, `ci`, `chore`, `refactor`. Lower-case imperative subject,
  at most about 70 characters; an optional body of one to three lines on why; no AI
  co-author trailer. Tests in their own `test(...)` commit, docs in one `docs(...)`
  commit per batch.
- **PRs**: the title uses the commit format; the body has these sections:

```markdown
## Summary
What changes and why. Base branch, work items, commits.

## Behavior and implementation
What the code does now, by component.

## Decisions to review
Choices a reviewer should confirm, each with the reason.

## Integration handoff
(Optional) What other work items need to know; merge conflicts.

## Validation
Tests run and their counts, manual checks, what was not checked.

## AI-assisted development
What was written with which AI tool; human review is the next step.
```
