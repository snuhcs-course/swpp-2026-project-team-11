# Metchu! backend

Django 5.2 server, on local SQLite or the team's shared Supabase Postgres
([Shared database](#shared-database-supabase-p8)). For now it holds the MVP's candidate set:
**the SNU cafeteria dishes of a given day**, split and merged into real dishes
([Daily menu preprocessing](#daily-menu-preprocessing-p7)) and each tagged by an LLM with the
features the question engines use.

The P10 question engine now consumes this candidate set. See the
[engine integration guide](question_engines/decision_tree/README.md) for its
Python API, interactive demo, snapshots, and paired benchmark. Its demo requires
no model API key when using the shared fixture.

The P13/P14 LLM engine (MVP2) consumes the same candidate set but sends only the
food names to Gemini. It needs the API key from step B.1 below. See the
[LLM engine guide](question_engines/llm/README.md) for its API, settings and
failure handling.

- Without `DATABASE_URL`, the DB is **one local file, `backend/db.sqlite3`**. It is gitignored, so everyone builds their own.
- With `DATABASE_URL`, everyone shares the team's Supabase DB (see below).
- Two ways to fill a DB:
  - **A. Load the shared snapshot**: no API key. Enough for engine development.
  - **B. Build any day yourself**: fetch that day's menu and tag it with Gemini using your own API key.

## 0. One-time setup

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate          # creates an empty db.sqlite3 (Restaurant / Food / MenuItem)
pytest                           # every backend test; no API key needed
```

## A. Load the shared snapshot (no API key)

```bash
python manage.py loaddata menus_2026-09-29
```

This loads `menus/fixtures/menus_2026-09-29.json`:
- 17 restaurants and 238 dishes, 208 of which are meal candidates
- all features already filled in

> **주의:** 스냅샷에는 2026-09-29 데이터만 있습니다. 날짜를 생략하면 "오늘" 기준이라 빈 목록이 나오니, 반드시 날짜를 넘기세요.
> 예: `--date 2026-09-29`, `services.get_candidates(datetime.date(2026, 9, 29))`

## B. Build a day's DB with your own API key

### 1) Put your key in `.env`

Create `.env` in the **repo root** (one level above `backend/`):

```bash
cp .env.example .env              # git bash / macOS
Copy-Item .env.example .env       # PowerShell
```

Its content is a single line. Get the key from [Google AI Studio](https://aistudio.google.com).

```
GOOGLE_API_KEY=your-key
```

`manage.py` loads it automatically (see `backend/env.py`). The LLM question engine reads the
same key; its optional settings are listed in the [LLM engine guide](question_engines/llm/README.md#configuration-and-failures-p14).

> **보안 규칙**
> - `.env`는 `.gitignore`에 있습니다. `git status`에 `.env`가 보이지 않아야 정상이며, **절대 커밋하지 마세요.**
> - 키를 채팅·카톡·Slack·이슈에 붙여 넣지 마세요.
> - 키는 서버에서만 씁니다. **Android 앱 코드에는 넣지 마세요** (APK를 풀면 그대로 보입니다).
> - 유출이 의심되면 AI Studio에서 키를 바로 삭제하고 새로 발급하세요.

Check that the key is picked up (prints `True`, never the key itself):

```bash
python -c "from env import load_env; import os; load_env(); print(bool(os.environ.get('GOOGLE_API_KEY')))"
```

If `GOOGLE_API_KEY` is already set as a Windows environment variable, that value wins over `.env`.

### 2) Fetch, preprocess and tag the day's menu

Today (Asia/Seoul), in one command:

```bash
python manage.py run_daily_pipeline --review review.csv
```

It runs `fetch_menus` (download, split combos, merge duplicates, store), `extract_features`
(tag the new dishes) and, with `--review`, writes the CSV for a person to check
([Daily menu preprocessing](#daily-menu-preprocessing-p7)). A specific day: `--date 2026-09-30`.
Siksha usually has the whole week's menu in advance.

The steps can also run one by one:

```bash
python manage.py fetch_menus --date 2026-09-30        # without a key: --no-llm, each new line stays one dish
python manage.py extract_features --date 2026-09-30
```

- Try a small batch first: `python manage.py extract_features --limit 25 --dry-run` prints tags without saving.
- On days with no menu (weekends, holidays), `fetch_menus` prints `오늘 운영 메뉴 없음` and exits.
- `fetch_menus` is safe to re-run; it replaces that day's menu items.
- `extract_features` skips dishes that are already tagged. Use `--force` to re-tag them.

### 3) Cost and consistency

- Lines on fixed menu boards are handled by the committed catalog with no LLM call. On 2026-10-13,
  167 of 206 lines were, and Gemini resolved the other 39 in 2 calls.
- On an empty database the first day also tags every dish (about 145, 6 calls). Lines and dishes
  resolved before are cached, so later days only pay for new ones.

> **주의:** LLM 결과는 실행할 때마다 조금씩 달라서, 각자 뽑은 feature 값이 서로 다를 수 있습니다.
> MVP1 vs MVP2 비교나 사용자 테스트처럼 **같은 조건이 필요한 경우에는 공유 스냅샷(방법 A)을 쓰세요.**

### 4) Inspect the result

```bash
python manage.py export_candidates --date 2026-09-30 --meal LU --output candidates.json
python manage.py createsuperuser && python manage.py runserver   # then http://127.0.0.1:8000/admin
```

To start over, delete `backend/db.sqlite3` and run `python manage.py migrate` again.

## Daily menu preprocessing (P7)

A cafeteria menu line is not always one dish. `fetch_menus` resolves every line into the dishes
it stands for before storing anything:

| Menu line | Becomes |
|---|---|
| 돈가스 카레우동 | 돈까스, 카레우동 (each lists 220동식당 and the combo price in its offers) |
| 즉석 마라탕 (75-1동), 마라탕 (공대간이식당) | one dish, 마라탕, with both cafeterias in its offers |
| 눈꽃 치즈 돈까스 / 눈꽃치즈 돈까스, 육회 비빔밥(S) / (L) | one dish each (spacing and size markers ignored by rule) |
| 공기밥, 탄산음료, 치즈스틱 2조각 | not a meal, not stored |
| 핫치킨버거, 통새우버거, 양념치킨, 후라이드치킨 | stay separate dishes |

Each line is answered by the first of these that knows it:

1. `menus/preprocess/overrides.json`: a person's corrections (always wins)
2. `menus/preprocess/fixed_menus.json`: the reviewed **fixed-menu catalog**
3. the `MenuLine` cache: lines resolved on an earlier day
4. Gemini (`gemini-3.5-flash`, structured output), only for lines never seen before
5. without a key (or `--no-llm`), or if Gemini fails: the whole line stays one dish, and the next run retries

**Fixed menus.** Half of a weekday's lines come from fixed boards (버거운버거, 공대간이식당,
220동식당, 75-1동 푸드코트) or fixed items in daily cafeterias (두레미담's order menu, 301동's
헬스팩). `build_fixed_menus` finds them in the menu history, resolves each once, and writes the
catalog, so they are handled the same way in every database. When a fixed board shows lines the
catalog does not know, `fetch_menus` warns; rebuild then (hand corrections in the file are kept):

```bash
python manage.py build_fixed_menus --start 2026-09-28 --end 2026-10-13 --review fixed_review.csv
```

**Human review.** Check the day's results in Excel and record corrections:

```bash
python manage.py export_preprocess_review --date 2026-10-13 --output review.csv   # no LLM call
```

Rows are `split` (a line split into dishes), `merge` (different lines that became one dish),
`not_meal`, and `maybe_same` (dish names that differ only by a word like 즉석 or 왕).
Mark wrong rows `N` and write the fix, then put it in `overrides.json`
(or in `fixed_menus.json` for a fixed line) and re-run `fetch_menus --date`:

```json
{"lines":  {"돈가스 카레우동": ["돈까스", "카레우동"], "공기밥": []},
 "dishes": {"즉석마라탕": "마라탕"}}
```

> **주의:** 이 파일들은 사람이 검토한 결과라 git으로 공유합니다. 고칠 때는 PR로 남겨 주세요.

## Shared database: Supabase (P8)

The team shares one Postgres database on Supabase, so every teammate's server sees the same
menu and the daily pipeline runs once for everyone. Each server reads it through `DATABASE_URL`;
without it nothing changes (local SQLite). **Tests always use SQLite**, even when `DATABASE_URL`
is set, so they never touch the shared data.

### Connect

1. Ask to be invited to the team's Supabase organization (or create the project: region
   **Northeast Asia (Seoul)**, Free plan, a DB password of letters and digits only).
2. In the project, open **Connect** and copy the **Session pooler** URI. The direct connection is
   IPv6-only on the free plan and often fails on campus and home networks; the pooler is IPv4.
3. Put it in the repo-root `.env`, with the real password in place of `[YOUR-PASSWORD]`:

```
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-<n>-ap-northeast-2.pooler.supabase.com:5432/postgres
```

4. Check: `python manage.py showmigrations menus` lists the migrations from Supabase.

> **보안 규칙:** `DATABASE_URL`에는 DB 비밀번호가 들어 있습니다. `.env`에만 두고 커밋·채팅에 올리지 마세요.
> 유출이 의심되면 Supabase에서 DB 비밀번호를 바로 바꾸세요. 앱(Android)은 Supabase에 직접 접속하지 않습니다.

### First-time setup (once per project)

```bash
python manage.py migrate                       # creates the tables in Supabase
python manage.py loaddata menus_2026-09-29     # the shared demo snapshot
python manage.py run_daily_pipeline            # today's menu
```

Then lock down Supabase's automatic API, which would otherwise expose these tables to anyone
with the project's public key: turn off the **Data API** in the project settings, and run this
once in the **SQL Editor** (Django owns the tables, so it is not affected):

```sql
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP; END $$;
```

Run it again after a migration that adds tables.

### Moving local data

Only needed for data that exists only in someone's local `db.sqlite3`. Dump it with
`DATABASE_URL` pointing at SQLite for that one command, then load it into Supabase:

```bash
DATABASE_URL=sqlite:///db.sqlite3 python -X utf8 manage.py dumpdata menus --indent 1 -o local_menus.json   # git bash
python manage.py loaddata local_menus.json
```

```powershell
$env:DATABASE_URL="sqlite:///db.sqlite3"; python -X utf8 manage.py dumpdata menus --indent 1 -o local_menus.json; Remove-Item Env:DATABASE_URL
python manage.py loaddata local_menus.json
```

`loaddata` resets the Postgres ID sequences by itself.

> **Free plan:** a project that sees little activity for 7 days is paused (restore it from the
> dashboard), and the database is limited to 500 MB. Running the pipeline daily keeps it active.

### Daily automation (GitHub Actions)

`.github/workflows/daily-menu.yml` runs `run_daily_pipeline` against the shared database
every day at **07:00 KST** (22:00 UTC), right after `migrate`. The day's review CSV is kept as
a run artifact for 14 days. Days without a menu (weekends, holidays) finish without changes.

Setup, once (needs admin rights on the repository):

1. **Settings → Secrets and variables → Actions → New repository secret**: add
   `DATABASE_URL` (the Session pooler URI above) and `GOOGLE_API_KEY`.
2. **Put the workflow on the default branch.** GitHub only runs scheduled and manual triggers
   for workflow files on the default branch, which is `main` today. Either set the default
   branch to `MVP` (**Settings → General → Default branch**) or merge `MVP` into `main`.
3. Test it: **Actions → Daily menu pipeline → Run workflow** (a date is optional).

- The job runs the code on `MVP`. To use another branch, set the repository variable
  `MENU_PIPELINE_REF`.
- A run fails when a secret is missing or when Gemini could not resolve every new line or tag
  every new dish (an expired key, an exhausted quota). What it could store is kept, the next run
  retries the rest, and GitHub emails the person who last changed the schedule in the workflow file.
- In a public repository, GitHub disables scheduled workflows after 60 days without repository
  activity; turn it back on from the Actions tab.
- The daily run also keeps the free Supabase project from pausing.

> **주의:** `GOOGLE_API_KEY` 시크릿에 넣은 키로 매일 Gemini가 몇 번 호출됩니다. 누구의 키를 쓸지 팀에서 정해 두세요.
> 새 테이블을 만드는 마이그레이션이 머지되면 위의 RLS SQL을 다시 실행하세요(이 작업이 `migrate`를 자동으로 돌립니다).

## Using it from the question engines (`menus/services.py`)

```python
import datetime
from menus import services

services.get_feature_schema()
# [{"key": "spicy", "question": "매콤한 게 당겨요?"}, ...]  (23 features)

services.get_candidates(datetime.date(2026, 9, 29), meal="LU")   # meal=None: whole day, date=None: today
# [{"food_id", "name", "display_name", "food_group",
#   "features": {"spicy": 0.9, "soupy": 1.0, ...},
#   "offers": [{"restaurant": "학생회관식당", "meal": "LU", "price": 3000}, ...]}, ...]

# New sessions load one matching version of candidates and questions together:
candidates, schema, version = services.get_catalog(datetime.date(2026, 10, 13), meal="LU")
```

The low-level readers above default to **v1** for existing callers. Recommendation
sessions and demo/benchmark commands use `get_catalog`: select `v2` only when every
candidate on the requested date and meal has `v2` features, and otherwise fall back
to `v1` (logging the served version and candidate counts, with a warning if a date/meal
is only partly `v2`). Candidates and questions always have the same version; legacy
meanings are never mixed and missing std is never invented. The 9/29 fixture and its
23 legacy scores remain unchanged.

### Feature extraction v2 (P11)

`schema.py` declares 33 features: 32 name-based measurements and deterministic
`meal_variety`. The accepted rubric is `menus/features/rubric.json`, version
`food-name-32-v2-mean-std-draft7`; `instructions.txt` supplies the common rules.
The extractor prompt contains no user questions, food filtering or combo splitting.
Filling uses the dish's usual one-person serving, including its conventional meal
composition; extra ingredients do not imply a larger serving. No dish-score
overrides are applied in code.

Each model measurement is `{"mean": number, "std": number}`. Mean is expected
feature intensity across ordinary recipes and serving styles; std describes
variation across those recipes, **not model confidence or a standard error**.
These are initial judgments from a name, not calibrated nutritional statistics
or response probabilities. No distribution family is assumed.

The DT default is now the `preference` policy (configurable on the server via
`METCHU_DT_POLICY=preference|greedy|lookahead` / `settings.RECOMMEND_DT_POLICY`):
explicit signed answers determine recommendation fit, and six-outcome expected
decision value determines questions and stopping, with a bounded two-question
check before proposing a food. Recipe std affects both fit and the answer
forecast. This policy has no default question-count cap or fixed
acceptance-probability threshold. The previous `greedy` and `lookahead` policies
remain available for comparison and runtime fallback.
See `question_engines/decision_tree/README.md` for utility units, assumptions,
regressions, and the distinction between fit and forecast probability.
Both numbers have at most two decimal places. Validation rejects nonfinite values,
mean outside [0,1], std outside [0,0.5], and
`std² > mean * (1 - mean)`; endpoints require zero std. Invalid output is retried,
never silently clipped or filled with 0.1/0.5.

Migration 0003 adds `Food.is_set=False` and `Food.feature_std={}`, preserving
old data and menu links. Identity is now `(name, is_set)`. After preprocessing,
two or more dishes in a line select set rows, regardless of mapping source.
The feature command evaluates each distinct name once and shares its 32
measurements across variants served on the target date (reusing any cached v2
variant from another date without modifying rows not served on the target date).
`features` remains a scalar mean dictionary; `feature_std` stores the matching
std dictionary. `meal_variety` is 1 for sets and 0 otherwise, always with std 0.
Set display names end in ` (세트)`. Existing food groups are preserved; new groups
are left empty rather than introducing a second model task.

Valid v2 data on an existing variant supplies a new variant without an API call.
`--force` reevaluates each name once, `--limit` counts distinct names, and failed
names keep their old version while the command exits with an error. `--dry-run`
still calls the model when needed, but writes nothing. Tests use fake responses.

For explicit v2 inspection, use:

```python
services.get_feature_schema("v2")
services.get_candidates(date, meal="LU", feature_version="v2", include_std=True)
```

`export_candidates` selects `v2` (including std) when every candidate on the
requested date/meal is `v2`, and falls back to `v1` otherwise; `--feature-version`
(`v1` or `v2`) forces a specific version. The default candidate reader
keeps its original keys. The DT integration uses `get_catalog` to enable v2
serving and std-aware question selection and answer updates. Its internal
candidate dictionaries carry std; REST reply shapes stay unchanged.

- Only real meals (`is_food=True`) are returned. Drinks, 공기밥 and side orders are excluded.
- Working in plain Python without Django? Read the JSON written by `export_candidates`.
- The feature list lives in `menus/features/schema.py`. If you change it, bump `FEATURE_VERSION` and re-run `extract_features`.

## Making a new shared snapshot

Use this to share your DB with the team. The file contains **every day** currently in your DB.

```bash
python -X utf8 manage.py dumpdata menus --indent 1 -o menus/fixtures/menus_2026-09-30.json
```

> **Windows 주의:** `-X utf8`을 빼면 파일이 cp949로 저장되어 한글이 깨질 수 있습니다.

Commit the file. Teammates then run `python manage.py loaddata menus_2026-09-30`.

## Command reference

| Command | What it does | API key |
|---|---|---|
| `migrate` | create the empty DB and tables | no |
| `loaddata menus_YYYY-MM-DD` | load a shared snapshot | no |
| `run_daily_pipeline [--date] [--review PATH]` | fetch + preprocess + tag a day (+ review CSV); runs daily on GitHub Actions | **yes** |
| `fetch_menus [--date] [--no-llm]` | fetch, preprocess and store a day's menu | for new lines |
| `extract_features [--date] [--limit N] [--dry-run] [--force]` | tag new dishes with features | **yes** |
| `build_fixed_menus [--start] [--end] [--review PATH]` | rebuild the fixed-menu catalog | for new lines |
| `export_preprocess_review [--date] --output PATH` | the day's results as a review CSV | no |
| `export_candidates [--date] [--meal] [--output]` | candidates + feature schema as JSON | no |
| `demo_llm_engine --date [--meal] [--smoke] [--output]` | run the MVP2 LLM question engine | **yes** |
| `serve_public [--port] [--write-client-config] [--debug]` | run the server behind a Cloudflare Tunnel, reachable from any network ([guide](../client/README.md#from-another-network-cloudflare-tunnel)); needs `cloudflared` | no |

## Data model (`menus/models.py`)

| Model | One row per | Notes |
|---|---|---|
| `Restaurant` | cafeteria | `code` is the Siksha id, e.g. `220동식당` |
| `Food` | distinct (dish name, set status) | recommendation unit; holds mean `features`, `feature_std`, preprocessing `is_food`, `display_name`, `food_group` |
| `MenuItem` | dish x restaurant x meal x day | `meal` is `BR` / `LU` / `DN`; `price` in won. A combo line has one row per dish |
| `MenuLine` | distinct menu line (`dish_key`) | cache of the dishes a line stands for (`is_meal`, `dishes`, `source`) |

## Data source

Menus come from the public [Siksha](https://siksha.wafflestudio.com) API by Waffle Studio.

- Endpoint: `https://siksha-api.wafflestudio.com/menus/?start_date=...&end_date=...`
- One request per day (`build_fixed_menus` fetches day by day; long ranges time out).
- The official SNU co-op page (`https://snuco.snu.ac.kr/foodmenu/`) is the planned fallback.
