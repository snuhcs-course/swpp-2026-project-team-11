# P21 human evaluation: what each person does

i3-P21 runs the LLM-user benchmark's setup with people. There are two parts:

- **Recommendation**: you play the decision tree, the RL policy and the LLM engine. You don't know which engine you are playing.
- **Features**: you judge whether the LLM's extracted dish features are reasonable.

Deadline: 2026-11-06. Testers and raters: 구본재, 김신서, 이민규, 이승호. Collector: 구본재.
Design and pass bars: [the benchmark README](../backend/question_engines/benchmark/README.md#user-study-p21)
and [the backend README](../backend/README.md#human-review-of-the-extracted-features-p21).

## Testers

Do part 1 before part 2: seeing the feature values first could change how you answer the
engines' questions. Use your name exactly as above in every command and file.

### Setup, once

Use the branch until the PR is merged, `main` after. The commands below are bash/zsh. In
PowerShell, replace `export X=value` with `$env:X = "value"`.

```bash
git fetch origin && git switch feat/i3-p21-human-eval
cd backend
pip install -r requirements.txt
export DATABASE_URL=sqlite:///p21.sqlite3      # a separate local DB, never the shared one
python manage.py migrate
python manage.py loaddata menus_2026-11-02
```

Set `DATABASE_URL` in every new terminal. Without it, `.env` can point the commands at the
shared database. The LLM engine's sessions need `OPENROUTER_API_KEY` in the repo-root `.env`.
Without it, the command stops with an error before a round starts. Each LLM session costs
about $0.01-0.02 on the team key.

### Part 1: recommendation, 4 rounds (12 sessions, about 30-40 minutes)

From `backend/`, with your name in place of `NAME`:

```bash
export DATABASE_URL=sqlite:///p21.sqlite3 METCHU_MAX_QUESTIONS=20
R=../engine_benchmark_results/2026-11-02
python manage.py play_engine_session --scenarios $R/scenarios.json --tester NAME \
    --output $R/9_user_study/human/NAME.jsonl
```

Each run plays one round. Run the same command four times, until it prints
`NAME: 4라운드를 모두 마쳤습니다`. A round goes like this:

1. **Pick your wish.** The menu is listed, and the prompt says what to pick:
   - one number: the menu you would most like to eat right now;
   - two or three numbers, comma-separated (`3,17`): different menus you would be equally happy with;
   - a dish name: a dish you want that is not on the list (it is refused if a kind of it is served);
   - one number from a list where each menu shows `~ 비슷한 메뉴`: in this round only that exact menu counts.

   Pick what you would really eat. Do not pick what you think is easy or hard for the app.
2. **Certainty.** Say honestly how sure you are of the wish: 1 sure, 2 mostly, 3 unsure.
3. **Three sessions.** You play the same wish on three hidden engines. Answer each question by
   its number as the person with that wish:
   - choose `잘 모르겠어요` when you cannot tell, and `상관없어요` when it does not matter;
   - start each session afresh and forget what earlier sessions asked or proposed;
   - do not try to steer the app.
4. **Proposals.** A menu you picked is accepted for you. In the `비슷한 메뉴` round, every other
   menu is rejected for you. Otherwise, answer `y` only if:
   - (served wish) the proposal is essentially the same dish: same kind, same main ingredients. A cheeseburger for a hamburger is `y`; galbi is `n`;
   - (wish not served) it would satisfy the same craving. A pork cutlet for a fish cutlet is `y`; jjajangmyeon is `n`.

   Five rejections end the session.
5. **Satisfaction.** After each session, rate it from 1 to 5: how happy you would be with how
   that session went (its result and the effort it took).

If you are interrupted (Ctrl-C, a network error), run the same command again. It continues the
round with the same wish and plays a failed session again. Do not edit or delete the `.jsonl`.

**Hand in** `engine_benchmark_results/2026-11-02/9_user_study/human/NAME.jsonl` to 구본재.

### Part 2: feature review (about 40 + 35 minutes)

Your files are in `feature_benchmark_results/2026-11-02-review/`:

- `cafeteria_NAME.xlsx` (39-40 dishes): ready now;
- `general_NAME.xlsx` (32-33 dishes): 구본재 adds it once the mini PC export arrives.

For each dish (row), read its means and stds, then fill only the yellow columns. The guide
is in the `안내` sheet and the rubric in the `루브릭` sheet.

| Column | What to enter |
|---|---|
| B `판정` | from the list: `합리적` no wrong feature, `일부 틀림` 1-3 wrong, `비합리적` 4 or more or the dish was taken for another, `판단 불가` you do not know the dish even after a look at recipes or photos |
| C `틀린 feature` | the wrong features' keys from row 4, comma-separated (`spicy, soupy`); required for `일부 틀림` |
| D `의견` | how it is wrong, briefly (`spicy 0.1 → 0.7`) |

A feature is wrong when:
- its mean is 0.3 or more off what the rubric gives the dish; or
- its std plainly contradicts how much the recipes vary (0 for a dish made many ways).

Smaller differences are not wrong. Work alone. Keep the rows, the other cells and the sheet
names as they are. Save as `.xlsx` under the same name. If you use Google Sheets, download it
back as `.xlsx`.

**Hand in** both workbooks to 구본재.

## Mini PC owner: now

The general menus' features exist only in the host's database. Export the general workbooks
read-only, from a copy of that database. Change nothing on the host.

1. Download the source of branch `feat/i3-p21-human-eval` into `%TEMP%\p21-review\src`:
   `https://github.com/snuhcs-course/swpp-2026-project-team-11/archive/refs/heads/feat/i3-p21-human-eval.zip`.
   Do not stage it under `releases/`.
2. Copy the database with SQLite's backup API, which is safe while the host runs, and point the
   commands at the copy:

```powershell
$py = "$env:LOCALAPPDATA\MetchuHost\venv\Scripts\python.exe"
New-Item -ItemType Directory -Force "$env:TEMP\p21-review" | Out-Null
& $py -c "import sqlite3,os; s=sqlite3.connect(os.path.expandvars(r'%LOCALAPPDATA%\MetchuHost\private\menu.sqlite3')); d=sqlite3.connect(os.path.expandvars(r'%TEMP%\p21-review\menu-copy.sqlite3')); s.backup(d); d.close(); s.close()"
$env:DATABASE_URL = "sqlite:///" + ("$env:TEMP\p21-review\menu-copy.sqlite3" -replace '\\','/')
$env:GOOGLE_API_KEY = "x-unused"; $env:OPENROUTER_API_KEY = "x-unused"; $env:OPENAI_API_KEY = "x-unused"
cd "$env:TEMP\p21-review\src\swpp-2026-project-team-11-feat-i3-p21-human-eval\backend"
& $py manage.py showmigrations menus      # if any are unapplied: & $py manage.py migrate (the copy only)
```

   The placeholder keys keep `.env` out (PowerShell drops an empty variable). No command here
   calls a model.
3. Export 100 dishes spread over the restaurant categories, 10 of them shared by all raters:

```powershell
& $py manage.py export_feature_review --stores --n 100 --raters 구본재,김신서,이민규,이승호 --output-dir "$env:TEMP\p21-review\out"
& $py manage.py shell -c "from menus.models import StoreMenu, Food; print(StoreMenu.objects.count(), Food.objects.filter(store_menus__isnull=False, feature_version='v2', is_food=True).distinct().count())"
```

   The export prints one line:
   `general: 음식 100개 (공통 10개), 검토자별 구본재 33, 김신서 33, 이민규 32, 이승호 32 -> ...`.
   The seed is fixed, so the same database gives the same sample.
4. **Return to 구본재:**
   - the five files in `%TEMP%\p21-review\out`: `general_구본재.xlsx`, `general_김신서.xlsx`, `general_이민규.xlsx`, `general_이승호.xlsx` and `general_assignment.csv` (100 dish rows);
   - the export's line, the two numbers of the shell command, and the time of the copy.

   Then delete `menu-copy.sqlite3`. If a step fails (a missing column, fewer than 100 dishes),
   stop and send the error output; do not work around it on the live database.

## Collector (구본재)

1. Commit the returned files to the PR branch:
   - the general workbooks into `feature_benchmark_results/2026-11-02-review/`;
   - each tester's `.jsonl` into `engine_benchmark_results/2026-11-02/9_user_study/human/`;
   - each rater's filled workbook in place of the blank one.

   Then tell the raters their general workbook is in.
2. Report, with no model call:

```bash
cd backend
R=../engine_benchmark_results/2026-11-02
python manage.py benchmark_engines --scenarios $R/scenarios.json --human $R/9_user_study/human/*.jsonl --output-dir $R
F=../feature_benchmark_results/2026-11-02-review
python manage.py report_feature_review --reviews $F/*.xlsx --output $F/report.md
```

3. Optionally, check the simulated user against people. This is a paid run on the simulated
   user's model: run it with `--dry-run` first, then without it, and rerun step 2 with
   `--simulator-check $R/9_user_study/simulator_check.jsonl`:

```bash
python manage.py validate_simulator --human $R/9_user_study/human/*.jsonl --output $R/9_user_study/simulator_check.jsonl --dry-run
```

4. Update the schedule row and the Testing Documentation wiki page with the results.
