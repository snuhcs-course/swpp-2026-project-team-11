# Metchu! backend

The live team deployment now uses the Windows mini PC and its local SQLite database.
See [host updates and rollback](../docs/mini-pc-host.md); the Supabase instructions
below describe the earlier deployment and recovery reference.

Django 5.2 server, on local SQLite or the team's shared Supabase Postgres
([Shared database](#shared-database-supabase-p8)). For now it holds the MVP's candidate set:
**the SNU cafeteria dishes of a given day**, split and merged into real dishes
([Daily menu preprocessing](#daily-menu-preprocessing-p7)) and each tagged by an LLM with the
features the question engines use. General menu mode adds the restaurants near
서울대입구역 and 낙성대역 ([General restaurants](#general-restaurants-near-the-stations-i3-p9)).

The P10 question engine now consumes this candidate set. See the
[engine integration guide](question_engines/decision_tree/README.md) for its
Python API, interactive demo, snapshots, and paired benchmark. Its demo requires
no model API key when using the shared fixture.

The P13/P14 LLM engine (MVP2) consumes the same candidate set but sends only the
food names to an LLM through OpenRouter. It needs `OPENROUTER_API_KEY` in the same
`.env` as step B.1 below. See the
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
python manage.py loaddata menus_2026-11-02
```

This loads `menus/fixtures/menus_2026-11-02.json`:
- 15 cafeterias and 127 dishes, all meal candidates
- v2 features (means and std) and allergen tags already filled in

> **주의:** 스냅샷에는 2026-11-02 데이터만 있습니다. 날짜를 생략하면 "오늘" 기준이라 빈 목록이 나오니, 반드시 날짜를 넘기세요.
> 예: `--date 2026-11-02`, `services.get_catalog(datetime.date(2026, 11, 2))[0]`

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

`manage.py` loads it automatically (see `backend/env.py`). To preprocess and tag with an OpenAI
model instead, add `METCHU_MENU_MODEL=openai:<model>` (e.g. `openai:gpt-5.4-mini`) and
`OPENAI_API_KEY` to the same file; see `backend/menus/llm.py`. The LLM question engine reads
`OPENROUTER_API_KEY` from the same file instead; it and the optional settings are listed in the [LLM engine guide](question_engines/llm/README.md#configuration-and-failures-p14).

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
(tag the new dishes), `extract_allergens` (tag their allergens, [Allergens](#allergens-i3-a1))
and, with `--review`, writes the CSV for a person to check
([Daily menu preprocessing](#daily-menu-preprocessing-p7)). A specific day: `--date 2026-09-30`.
Siksha usually has the whole week's menu in advance.

The steps can also run one by one:

```bash
python manage.py fetch_menus --date 2026-09-30        # without a key: --no-llm, each new line stays one dish
python manage.py extract_features --date 2026-09-30
python manage.py extract_allergens --date 2026-09-30
```

- Try a small batch first: `python manage.py extract_features --limit 25 --dry-run` prints tags without saving.
- On days with no menu (no Siksha menu and no fixed board, e.g. Sundays), `fetch_menus` prints
  `오늘 운영 메뉴 없음` and exits. A fixed board does not know holidays: it is added on each of its weekdays.
- `fetch_menus` is safe to re-run; it replaces that day's menu items.
- `extract_features` and `extract_allergens` skip dishes that are already tagged. Use `--force` to re-tag them.

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

## Short menu display names

Every candidate keeps the original sales line in `name`. Its `display_name` starts
with `clean_name(raw_name)[0]`; if that base exceeds 20 characters or contains
characters other than letters, digits, whitespace and parentheses, a current
`MenuLabel` can replace it. Without a current label the cleaned base is shown.
The rule applies to both cafeteria and restaurant sales menus. The restaurant
catalogue caches the labels with the menu for up to `RECOMMEND_STORE_MENU_CACHE_S`.

`tag_menu_labels --date YYYY-MM-DD`, `--stores`, and `--all` select the menu
lines to label. The command deduplicates by the original line and skips labels at
`LABEL_VERSION`; `--force` refreshes them. `--dry-run` makes no model call and
writes nothing. It prints the number of distinct names, initial batches and the
maximum calls if every item requires a single-item retry. A real run uses the
configured menu model and can incur costs; review its count first. It saves
successful batches even if other names fail; rerun to retry failures.
`run_daily_pipeline` includes the date-scoped label step.

Labels are estimates for presentation, not menu, allergen or feature corrections.
The preprocessing prompt and `PREPROCESS_VERSION` are unchanged.



## Interaction logs

Set `METCHU_INTERACTION_LOG_DIR` to a private directory to collect server-side
interaction events. It is disabled when unset. The server appends one JSON line
for each session start, answer, recommendation request, feedback, undo or ban.
Events include a random session-specific logging ID, UTC time, engine, meal,
menu date, source and distance scope, candidate counts before and after the distance filter,
and the server-generated question or recommendation step. Recommendations include
the dish ID, display name and up to ten restaurant names. Validated user location
and allergy choices are recorded once at session start. No IP, device identifier,
API session token, question text, explanation text or raw request body is recorded.

Files use UTC dates (`interactions-YYYY-MM-DD.jsonl`). The current day and previous
29 calendar days are retained; the running server prunes older matching files at
startup and hourly, even when no sessions occur. Logs are outside the recommendation
DB, which can stay read-only. A file error is reported to the operational log and
never fails a recommendation request. The current writer is thread-safe within one
server process. Keep the directory private; these records include sensitive location
and allergy selections.

Only server requests and resulting steps are captured: app-only navigation, a
request that never reaches the server, and a confirmed session end are not tracked.
The session ID in the log is independent of the public API session token; it is not
a persistent user identifier. Do not treat missing later events as proof that a user
accepted, quit or was dissatisfied.

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

**Cafeterias Siksha does not list.** `menus/data/fixed_cafeterias.json` holds their boards: 구시아푸드마켓
(300동) from 2026-11-03, every meal Monday to Saturday. `fetch_menus` adds a board's lines to every
day it serves, so they go through the same preprocessing, tagging and allergy filter, and a session
offers them like any cafeteria. A corner is named like Siksha's 자하연식당>2층 (구시아푸드마켓>비비고고);
the map shows one pin at 300동. When a board changes, edit the file; when Siksha starts listing a cafeteria, delete its entry, or its
lines are offered twice. The SETs with a plate of 제육 are split in `overrides.json`.

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

## General restaurants near the stations (i3-P9)

General menu mode recommends from the restaurants near 서울대입구역 and 낙성대역 instead of the
cafeterias. Their menu boards come from a crawl: the 소상공인시장진흥공단 상가(상권)정보 stores within
600 m / 500 m of the stations, each matched to its Naver Place menu by `fetch_naver_menus`
(i3-A2). The snapshot is committed as `menus/data/naver_menus_YYYY-MM-DD.json`; the format
`import_stores` reads is in `menus/sources/naver_stores.py`. The crawl is not daily: import
a new snapshot whenever the stores are crawled again. It replaces the menus of the earlier import,
so a file with failed stores, or fewer stores than its `counts` say, is refused: `--allow-partial`
imports it and keeps the earlier menus of those stores. The snapshot is added by #22.

```bash
S=menus/data/naver_menus_2026-11-02.json
python manage.py import_stores --file $S --dry-run                     # no LLM call, no write
python manage.py import_stores --file $S --limit 30 --review review.csv  # try on a local DB
python manage.py run_store_pipeline --file $S --review review.csv      # import + features + allergens
```

- **Restaurants.** Matched stores with a menu are kept. Cafes, bakeries and dessert shops are left
  out (상가정보 중분류 `비알코올`, a bakery or dessert 소분류, or such a Naver category). Bars stay.
- **Menu lines.** Rules drop banners and notices ("🔥 중식은 불향이 반입니다 🔥": no price and
  framed by decorations, sentence-like or a notice word; "★모둠회" stays) and drinks (소주, 생맥주
  500cc, 콜라) for free. The LLM
  resolves the rest with the cafeteria's dish rules (`menus/preprocess/store_prompt.py`), using the
  restaurant's category and the menu description: it splits sets ("A세트: 짜장면+탕수육(소)"), drops
  side dishes such as 마른안주, and leaves a vague line with no description ("점심특선") without a dish.
- **Shared dishes.** A dish has the same name and the same `Food` row as in the cafeterias, so its
  features are extracted once. `extract_features --stores` tags only the new ones.
- **Allergens per menu line.** The dishes kept for recommendation leave sides out, so
  `extract_allergens --stores` tags each whole line with its description ("낙지볶음+계란찜" may
  contain egg) in `StoreMenu.allergens`; a session with allergies leaves out lines whose tags match
  or are not current. Tags carry over to the same line (name and description) in a new snapshot.
- **Cache.** Answers are cached in `MenuLine` under `store:` keys and `STORE_VERSION`, apart from the
  cafeteria lines. A key holds everything the LLM sees: the name, the restaurant's category and the
  description (its first 60 characters). "A세트" is also keyed by its restaurant.
- **Review.** `--review` adds `rule_notice` / `rule_drink` (dropped by a rule) and `unnamed` rows to
  the usual ones. Corrections go into `overrides.json`; a vague line is written with its restaurant,
  as the CSV shows it: `{"lines": {"A세트 @홍콩반점 낙성대점": ["짜장면", "탕수육"]}}`.
- **Sessions.** `POST /api/sessions/` with `"source": "general"` serves these dishes
  (`services.get_store_catalog`). Offers keep the cafeteria shape, with the session's meal (the
  current one in Seoul when the session has none). The menus are read from the database at most
  every `RECOMMEND_STORE_MENU_CACHE_S` seconds (5 minutes), so an import shows within that time.
  The default general engine is the decision tree. Use `"engine": "rl"` for feature-only
  RL, or set `METCHU_ENGINE=rl` for clients that omit the engine. General sessions reject
  the LLM option. DT setup takes about 0.1 s with 500, 1 s with 2,000 and 5 s with 4,000
  candidates. `"source": "all"` combines cafeteria and restaurant menus, preserves both
  sources' allergy filters. `distance_scope=near` filters offers to 800 m straight-line
  distance before recommendation when location is known; without it, all remain.
  `distance_scope=any` has no distance cutoff. Like `general`, this supports DT and RL;
  an explicit LLM request is rejected.
- **Pipeline.** If `import_stores` fails (a quota error), `run_store_pipeline` stops before tagging:
  the lines it stored as they read are replaced by the next run.

> **주의:** `--dry-run`이 LLM에 보낼 줄 수를 알려 줍니다. 실제 실행 전에 호출 수를 확인하세요. 2026-11-02 스냅샷은 640곳, 서로 다른 메뉴 줄 9,659개로 전처리 호출이 약 387회, 알레르기 호출이 약 366회입니다.
> 머지 후 첫 07:00 매일 작업의 `migrate`가 Supabase에 새 테이블 `menus_storemenu`를 만듭니다. 그 뒤 RLS SQL을 다시 실행하세요.

## Accounts (i4-P6)

Signing in is optional; it is there so that the group mode can tell users apart.
`accounts/` keeps Django's own `auth.User` (a username and a PBKDF2 password hash) and adds
two tables: `AuthToken`, one per signed-in device, holding only the SHA-256 of the token the
app sends as `Authorization: Token <token>`, and `GoogleIdentity`, the Google account (its
stable `sub` and, when Google verified it, the address) linked to a user. The full API is in
the docstring of `accounts/views.py`:

| Request | Body | Reply |
| --- | --- | --- |
| `POST /api/auth/signup/` | `{"username", "password"}` | 201 `{"token", "user"}` |
| `POST /api/auth/login/` | `{"username", "password"}` | `{"token", "user"}` |
| `POST /api/auth/google/` | `{"id_token"}` | `{"token", "user", "created"}`, 201 for a new account |
| `POST /api/auth/google/link/` | `{"id_token"}`, signed in | `{"user"}` |
| `GET /api/auth/me/` | signed in | `{"user"}` |
| `POST /api/auth/logout/` | signed in | 204, ends this device's token only |

`user` is `{"username", "google_email", "has_password"}`. Usernames are 3–30 letters, digits or
`. @ + - _`, unique ignoring case; passwords must pass `AUTH_PASSWORD_VALIDATORS`. A wrong
username and a wrong password get the same 401. Google sign-in makes an account named after the
address, without a password, the first time; linking lets an existing account sign in either way.

Google sign-in needs `METCHU_GOOGLE_CLIENT_ID`, the client ID of the team's **web** OAuth client
(the app's `metchu.googleWebClientId`, see client/README.md); without it those two requests answer
503 and password accounts still work. The server checks each ID token with `google-auth`
(signature, expiry, issuer and that audience); that fetches Google's public keys, so it needs the
network. Tests patch the check and need neither. Recommendation sessions do not read the token yet.

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
python manage.py loaddata menus_2026-11-02     # the shared demo snapshot
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
   `DATABASE_URL` (the Session pooler URI above) and `GOOGLE_API_KEY`. To run the menu steps
   on OpenAI instead, also add the secret `OPENAI_API_KEY` and, under **Variables**, the
   repository variable `METCHU_MENU_MODEL` (e.g. `openai:gpt-5.4-mini`). Deleting the variable
   goes back to Gemini.
2. **Keep `main` the default branch** (**Settings → General → Default branch**). GitHub only
   runs scheduled and manual triggers for workflow files on the default branch.
3. Test it: **Actions → Daily menu pipeline → Run workflow** (a date is optional).

- The job runs the code on `main`. To use another branch, set the repository variable
  `MENU_PIPELINE_REF`.
- A run fails when a secret is missing (the key of the configured model) or when the model
  could not resolve every new line or tag every new dish (an expired key, an exhausted quota).
  What it could store is kept, the next run retries the rest, and GitHub emails the person who
  last changed the schedule in the workflow file.
- In a public repository, GitHub disables scheduled workflows after 60 days without repository
  activity; turn it back on from the Actions tab.
- The daily run also keeps the free Supabase project from pausing.

> **주의:** 설정한 모델의 키(`GOOGLE_API_KEY` 또는 `OPENAI_API_KEY` 시크릿)로 매일 LLM이 몇 번 호출됩니다. 누구의 키를 쓸지 팀에서 정해 두세요.
> 새 테이블을 만드는 마이그레이션이 머지되면 위의 RLS SQL을 다시 실행하세요(이 작업이 `migrate`를 자동으로 돌립니다).

## Using it from the question engines (`menus/services.py`)

```python
import datetime
from menus import services

services.get_feature_schema()
# [{"key": "spicy", "question": "Do you feel like something spicy?",
#   "question_en": "...", "family": "taste"}, ...]  (33 features)

candidates, schema = services.get_catalog(datetime.date(2026, 11, 2), meal="LU")   # meal=None: whole day, date=None: today
# One candidate per sales menu, named as the restaurant lists it:
# [{"food_id", "name", "display_name", "food_group", "menu_profile": "rms-v1",
#   "features": {"spicy": 0.9, "soupy": 1.0, ...}, "feature_std": {"spicy": 0.1, ...},
#   "offers": [{"restaurant": "학생회관식당", "meal": "LU", "price": 3000,
#               "lat": 37.45932, "lng": 126.95058}, ...]}, ...]

# The same for the restaurants near the stations (offers carry the given meal):
candidates, schema = services.get_store_catalog(meal="DN")
```

A menu is a candidate only when every main dish is tagged with the current
`FEATURE_VERSION` (v2); `get_catalog` logs how many of the served menus it kept.

### Actual menu candidates and feature profiles

`get_catalog` and `get_store_catalog` return `(candidates, schema)`. Candidates
preserve the purchasable dish/set title, whole price and restaurant offers; only
mechanical source prices and notices are stripped from titles. Imported menu-level
profiles take precedence over the RMS of complete current-version main vectors.
Malformed, stale or incomplete menus are withheld without breaking other menus.

`food_id` belongs to the durable sales-menu registry. It is independent of source
row replacements, prices and dates, and is not a `Food` primary key. Raw source
names, descriptions and source namespaces define recipe identity, so changed
recipes/size variants remain separate. Pure-engine callers can still use groups;
actual-menu catalogues disable them.

See [profile import, identity and deployment](../docs/menu-profiles.md). Collected
menus, generated features and checkpoints belong outside Git, for example in
`.local/menus/`. Importing profiles makes no model calls. New catalogue features
alone do not retrain the frozen RL policy or establish human recommendation accuracy.

### Feature-only RL

Select **Reinforcement learning (RL)** in Android Settings or send `"engine": "rl"`
to `POST /api/sessions/`. Both cafeteria and general sessions use v2 dish features
after allergy and distance filtering. An empty catalogue returns an unavailable step.

The frozen v20 policy ranks dishes from their features and the user's answers.
After a refusal it excludes that dish and updates the scores of similar dishes
before choosing whether to ask or propose again. Matching catalogues share
numeric arrays; answers, refusals, offers and undo history belong to the session.
Inference uses NumPy on CPU. The source checkpoint hash is in
[`weights.json`](question_engines/rl/weights.json).

From `backend/`, run `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m question_engines.rl.benchmark`
to measure preparation and the first decision on synthetic menus of 500–12,000 dishes.

### Allergens (i3-A1)

A user's allergies are a hard rule. `POST /api/sessions/` takes `"allergies"`, a list of
keys from `menus/allergens.py` (the 19 allergens Korean food labels must declare: `egg`,
`milk`, `buckwheat`, `peanut`, `soybean`, `wheat`, `mackerel`, `crab`, `shrimp`, `pork`,
`peach`, `tomato`, `sulfite`, `walnut`, `chicken`, `beef`, `squid`, `shellfish`, `pine_nut`).
`get_catalog(date, meal, allergies)` then drops every menu line with a dish tagged with one of
them **or a dish without current tags**, before the selected engine sees the candidates. A combo line
("돈가스 카레우동") is bought whole, so 카레우동 is not offered there to someone allergic to pork,
though it can still be offered where it is served alone. The feature version is chosen among
the dishes that are left. Without allergies nothing changes. The phone keeps the allergies; the server does not store them, also for a signed-in user (see "Accounts").

The result screen can also ban a food group, or a menu without one, for the rest of
the session (i3-A14): `POST /api/sessions/<id>/ban/` takes a `food_group` or the
candidate's `food_id`. Rather than changing the engines, the session turns down any
guess of a banned menu with `feedback` as soon as an action reaches it, and an undo
that reaches one goes back further, so it does not return after Back either. A new
session starts with no bans. The phone offers a group ban once the group makes up two
of the last three proposals. A menu is left out when any of its dishes is in a banned
group: each candidate's `food_groups` lists them, a set dish taking the group of its
single variant, so banning 버거 also leaves out the 버거운버거 sets. New dishes get no
`food_group` (only rows that already had one keep it); a menu without any is banned
one menu at a time.

`extract_allergens` asks the menu model which allergens each dish name may contain, sauces,
broths and batters included; the prompt tells it to leave a key out only when it is sure.
It runs once per name (about one call per 25 new names) and stores `Food.allergens` with
`Food.allergen_version`. Changing the list or the prompt bumps `ALLERGEN_VERSION`, after
which every food counts as untagged until it is tagged again. The tags are an estimate from
names, not cafeteria data, and the app says so.

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
Existing food groups are preserved; new groups are left empty rather than
introducing a second model task. Recommendation names come from the original menu line.

Valid v2 data on an existing variant supplies a new variant without an API call.
`--force` reevaluates each name once, `--limit` counts distinct names, and failed
names keep their old version while the command exits with an error. `--dry-run`
still calls the model when needed, but writes nothing. Tests use fake responses.

`export_candidates` writes the same candidates, std included. The decision tree uses
the std for question selection and answer updates; REST reply shapes do not carry it.

- Only real meals (`is_food=True`) are returned. Drinks, 공기밥 and side orders are excluded.
- Working in plain Python without Django? Read the JSON written by `export_candidates`.
- The feature list lives in `menus/features/schema.py`. If you change it, bump `FEATURE_VERSION` and re-run `extract_features`.

## Feature extraction benchmark (P12)

Benchmarks are experiments that inform design choices; tests check that the code works.
`menus/features/benchmark/` measures how good the extracted mean/std values are, as far as
that can be measured. One command runs it end to end and keeps everything in
`feature_benchmark_results/NAME/`, committed so the team shares runs, reports and rating
forms (`benchmark_features` alone writes to the gitignored `feature_benchmark_report/`).
Running the same name again continues a stopped run and rewrites the report. Its
extraction settings (dishes, model, prompt version, seed, batch size, git commit) are kept
in `config.json` from the first extractions, and a rerun with other settings is refused, so a
folder never mixes two setups; `collect_feature_runs` likewise refuses to continue a run made
with another model or prompt. A git commit ending in `-dirty` had uncommitted changes:

```
NAME/
  config.json              extraction settings (fixed), conditions, ratings, git commits
  report.md, summary.json  every section's results
  runs/runs.jsonl          every extraction
  1_integrity/ 2_distribution/ 3_stability/ 4_human_reference/ 5_triplets/ 6_downstream_impact/
  4_human_reference/forms/     blank rating forms and the LLM's answers in the same format
  4_human_reference/ratings/   the raters' filled copies, read when --ratings is not given
```

```bash
python manage.py run_feature_benchmark --name 2026-10-20 --date 2026-10-20 --dry-run   # LLM calls only
python manage.py run_feature_benchmark --name 2026-10-20 --date 2026-10-20
R=../feature_benchmark_results/2026-10-20
python manage.py export_feature_rating_form --runs $R/runs/runs.jsonl \
    --output $R/4_human_reference/forms/rating_form.xlsx --all invariant --close variant --n 0
# filled copies into $R/4_human_reference/ratings/, then the same run adds sections 4 and 6:
python manage.py run_feature_benchmark --name 2026-10-20 --date 2026-10-20
```

The steps it runs can also be used one by one. Only `collect_feature_runs` costs API calls:

```bash
python manage.py build_eval_menu_set --output menu_set.json                    # variant / invariant dishes of past days
python manage.py collect_feature_runs --menu-set menu_set.json --output runs.jsonl --condition repeat --dry-run
python manage.py collect_feature_runs --menu-set menu_set.json --output runs.jsonl --condition repeat
python manage.py collect_feature_runs --menu-set menu_set.json --output runs.jsonl --condition shuffle_foods
python manage.py collect_feature_runs --menu-set menu_set.json --output runs.jsonl --condition shuffle_features
python manage.py export_feature_rating_form --runs runs.jsonl --output rating_form.xlsx \
    --all invariant --close variant --n 0                                     # one copy per rater
python manage.py benchmark_features --runs runs.jsonl --ratings kim.xlsx lee.xlsx         # no LLM call
```

| Section | What it measures | Needs |
|---|---|---|
| 1. Integrity | 33 keys (32 measured + `meal_variety` for stored foods), bounds, two decimals, std² <= mean(1 - mean). The only pass/fail | any run |
| 2. Distribution | each feature's histogram of means, and dish pairs the features cannot tell apart (collisions) | any run |
| 3. Stability | spread over repeated runs: `repeat`, `shuffle_foods` (batch neighbours), `shuffle_features` (rubric order); each dish over all its runs | 2+ runs per condition |
| 4. Human reference | LLM means and stds against human ratings, next to how far raters are from each other on the same dishes | `--ratings` |
| 5. Triplets | "anchor is closer to near than to far", by kind (`close` / `distinct`) and source (`ai` / `human`) | the triplet dishes |
| 6. Downstream impact | the decision tree with AI vs human features, same policy and simulated user: first-pick acceptance, interactions to acceptance | `--ratings` |

- Sections 2-4 are also reported apart for variant dishes (daily menus) and invariant dishes
  (the fixed-menu catalog). `--date D` instead of `--menu-set` takes one day from the database,
  and `--stored` copies its v2 features as a run with no LLM call, into a file of its own (it
  has 33 keys, extraction runs 32).
- Stability: the default conditions have 3 `repeat` runs and 2 of each shuffle. An SD from two
  runs is noisy, so small differences between conditions are not meaningful; the report says so.
- Human reference, the ratio (LLM-to-rater gap over rater-to-rater gap): about 1 means the LLM
  looks like one more rater; an LLM at the raters' true average would score about 0.7 (1/√2).
- The rating form has a `<feature>_mean` and `<feature>_std` column per rubric feature and a
  `recipe_notes` column. A `.xlsx` form checks the input as raters type and carries the guide
  and the rubric; a `.csv` form is the same columns as plain text. Raters use the extractor's
  rubric (`menus/features/instructions.txt`, `rubric.json`) and look at real recipes or serving
  examples before judging a std.
- The form's dishes: `--all KIND` takes every dish of a kind, `--close KIND` each dish of a kind
  whose closest dish is a collision, with that dish (can raters tell them apart?), and `--n` a
  sample of the rest. A `kind` column shows 고정 메뉴 / 매일 바뀌는 메뉴 / 비교용 예시 (triplet-only);
  rows are grouped by it and shuffled within; `<output>_selection.csv` keeps why each dish is there.
  `--llm-values` writes the same form filled with the LLM's answers (averaged over the runs) to
  set side by side with the raters' copies; it is not a rating, so do not pass it to `--ratings`.
- Triplets are a JSON list or CSV of `anchor, near, far, kind, source, note`;
  `menus/features/benchmark/data/triplets.json` is an AI draft, and `--triplets` takes another file.
- The downstream simulated user is the decision tree's `ResponseOracle`. Its answer
  probabilities are assumptions that real user logs should calibrate once the app records them.
- Downstream favours the human features by design: the simulated user answers from them, so
  the human-feature engine plays against its own truth. The gap measures how much the AI
  features' disagreement with the raters changes recommendations, not that human features
  recommend better.
- `feature_benchmark_results/2026-10-20-luna/` was collected at `e76162b` with the menu model
  setting (#12) applied but not yet committed, hence `e76162b-dirty` in its config. The prompts
  are unchanged since: every run's `prompt_hash` matches the prompt this code builds.

## Making a new shared snapshot

The snapshot holds one day: its menu items and the cafeterias and dishes they use. Every
dish must already carry v2 features. To make one from the DB you use (the shared Supabase
is only read):

```bash
python -X utf8 manage.py shell -c "
import datetime
from django.core import serializers
from menus.models import Food, MenuItem, Restaurant
items = MenuItem.objects.filter(date=datetime.date(2026, 11, 2)).order_by('pk')
objects = [*Restaurant.objects.filter(pk__in=items.values('restaurant_id')).order_by('pk'),
           *Food.objects.filter(pk__in=items.values('food_id')).order_by('pk'), *items]
with open('menus/fixtures/menus_2026-11-02.json', 'w', encoding='utf-8') as f:
    serializers.serialize('json', objects, indent=1, ensure_ascii=False, stream=f)
"
```

> **Windows 주의:** `-X utf8`을 빼면 파일이 cp949로 저장되어 한글이 깨질 수 있습니다.

Replace the old snapshot, update the date in the tests, docs and `METCHU_MENU_DATE` examples,
and commit. Teammates then run `python manage.py loaddata menus_<date>`.

## Command reference

| Command | What it does | API key |
|---|---|---|
| `migrate` | create the empty DB and tables | no |
| `loaddata menus_YYYY-MM-DD` | load a shared snapshot | no |
| `run_daily_pipeline [--date] [--review PATH]` | fetch + preprocess + tag a day (+ review CSV); runs daily on GitHub Actions | **yes** |
| `fetch_menus [--date] [--no-llm]` | fetch, preprocess and store a day's menu | for new lines |
| `extract_features [--date \\| --stores] [--limit N] [--dry-run] [--force]` | tag new dishes with features | **yes** |
| `extract_allergens [--date \\| --stores] [--limit N] [--dry-run] [--force]` | tag new dishes (with `--stores`, restaurant menu lines) with the allergens they may contain | **yes** |
| `fetch_naver_menus --stores CSV --output PATH` | save the Naver Place menus of the food shops near 서울대입구역 and 낙성대역 to JSON | no |
| `import_stores --file [--dry-run] [--limit N] [--allow-partial] [--no-llm] [--review PATH]` | import the restaurants near the stations from a crawl file | for new lines |
| `run_store_pipeline --file [--review PATH]` | import + tag the restaurants near the stations | **yes** |
| `build_fixed_menus [--start] [--end] [--review PATH]` | rebuild the fixed-menu catalog | for new lines |
| `export_preprocess_review [--date] --output PATH` | the day's results as a review CSV | no |
| `export_candidates [--date] [--meal] [--output]` | candidates + feature schema as JSON | no |
| `build_eval_menu_set --output [--start] [--end] [--dry-run]` | variant and invariant dishes of past days, for the benchmark | for new lines |
| `collect_feature_runs --output --condition [--menu-set \\| --date] [--repeats] [--stored] [--dry-run]` | extract dishes repeatedly for the benchmark | **yes** (not with `--stored`) |
| `export_feature_rating_form --runs --output [--all] [--close] [--n] [--segment] [--llm-values]` | blank human rating form, or the LLM's answers in its format | no |
| `run_feature_benchmark --name (--menu-set \\| --date) [--conditions] [--ratings ...] [--dry-run]` | the whole benchmark into `feature_benchmark_results/NAME/` | **yes** |
| `benchmark_features --runs [--ratings ...] [--triplets] [--policy]` | the feature extraction benchmark report | no |
| `serve_public [--port] [--write-client-config] [--debug]` | run the server behind a Cloudflare Tunnel, reachable from any network ([guide](../client/README.md#from-another-network-cloudflare-tunnel)); needs `cloudflared` | no |
| `demo_llm_engine --date [--meal] [--smoke] [--output]` | run the MVP2 LLM question engine | **yes** (OpenRouter) |
| `run_engine_benchmark --name [--date ...] [--counts] [--repeats] [--limit] [--dry-run]` | the question engine benchmark into `engine_benchmark_results/NAME/` ([guide](question_engines/benchmark/README.md)) | **yes** (OpenRouter + simulated user) |
| `build_engine_scenarios` / `collect_engine_sessions` / `benchmark_engines` | its steps one by one; only `collect_engine_sessions` calls an LLM | for sessions |
| `play_engine_session --scenarios --output --tester` / `validate_simulator` | the benchmark's user study: a person plays, engine hidden | for LLM sessions |

## Data model (`menus/models.py`)

| Model | One row per | Notes |
|---|---|---|
| `Restaurant` | cafeteria or restaurant | `source` `siksha`: `code` is the Siksha id, e.g. `220동식당`; `lat`/`lng` come from Siksha and are null when it has none. `source` `naver`: `code` is the 상가업소번호, with `category`, `address` and the Naver `place_id` |
| `Food` | distinct (dish name, set status) | a main dish of a sales menu; holds mean `features`, `feature_std`, preprocessing `is_food`, `food_group`, `allergens`. Users see the menu line's `raw_name`, never this name |
| `MenuItem` | dish x restaurant x meal x day | `meal` is `BR` / `LU` / `DN`; `price` in won. A combo line has one row per dish |
| `StoreMenu` | dish x restaurant menu line | the menu boards of the restaurants near the stations; no date or meal. A set has one row per dish; `allergens` are the whole line's |
| `MenuLine` | distinct menu line (`dish_key`) | cache of the dishes a line stands for (`is_meal`, `dishes`, `source`); restaurant lines use `store:` keys |

## Data source

Menus come from the public [Siksha](https://siksha.wafflestudio.com) API by Waffle Studio.

- Endpoint: `https://siksha-api.wafflestudio.com/menus/?start_date=...&end_date=...`
- One request per day (`build_fixed_menus` fetches day by day; long ranges time out).
- The official SNU co-op page (`https://snuco.snu.ac.kr/foodmenu/`) is the planned fallback.

### Naver Place menus of shops near the stations (i3-A2)

The shop list comes from 소상공인시장진흥공단 상가(상권)정보 (data.go.kr, a quarterly
zip of CSVs per province; unzip the 서울 one, about 300 MB). `menus/sources/stores.py`
reads its food shops (대분류 `I2`) other than cafés, bakeries, rice-cake shops and ice
cream. The menus come from Naver Place: Naver has no official API that returns menus
(the Search API's local search and the NCP Maps APIs give names and coordinates only),
so `menus/sources/naver.py` reads the public mobile pages a signed-out visitor sees:

- List: `https://m.place.naver.com/restaurant/list?query=...&x=<lng>&y=<lat>`, searched
  with the shop's name and branch near the shop. The match is the nearest place within
  150 m whose name contains the shop's name (ignoring spaces, case and symbols).
- Menu: `https://m.place.naver.com/restaurant/<place id>/menu/list`. A menu shown only as
  photos gives no items; a price that is not a single amount ("변동", a range) is `null`.
- Both pages embed `window.__APOLLO_STATE__`; if Naver changes it, parsing raises
  `ValueError`. Naver answers non-browser user agents with 429, so a mobile browser's is sent.
  Requests are a second apart.

```bash
python manage.py fetch_naver_menus --stores PATH/소상공인시장진흥공단_상가(상권)정보_서울_202609.csv \
    --output menus/data/naver_menus_YYYY-MM-DD.json
```

`AREAS` in the command sets the stations and radii (서울대입구역 600 m, 낙성대역 500 m):
1132 shops in the 2026-09 file, so about 2000 requests and 40 minutes. Each shop is kept
with a `status`: `matched` (with `naver` and `menus`), `not_found` (Naver lists no such
place nearby, or the shop has closed) or `failed` (a request failed). After five failures
in a row the command writes what it has and exits with an error.

It goes to a JSON file. `import_stores` cleans its menus (drinks, notices, per-person fees)
and puts them into the DB as `StoreMenu`; see
[General restaurants](#general-restaurants-near-the-stations-i3-p9).

#### Committed snapshot: `menus/data/naver_menus_2026-11-02.json`

- Shops: `소상공인시장진흥공단_상가(상권)정보_서울_202609.csv`, from the data.go.kr zip
  `소상공인시장진흥공단_상가(상권)정보_20260930.zip`.
- Menus: Naver Place, fetched on 2026-11-02 from 15:28 to 16:19 KST (51 minutes) with the
  command above, from one machine, signed out, a second between requests.
- Result: 1132 shops in the radii; 809 matched (서울대입구역 581 of 826, 낙성대역 229 of 307),
  323 not found, 0 failed; 11,464 menu items. 149 matched places list their menu only as
  photos and have no items.
- Check: 12 random matches were all the same shop; the two sources' coordinates differ by
  at most 125 m (90% within 12 m). Shops not found are mostly not real names
  ("그외기타간이음식점"), karaoke and hold'em bars, closed shops, and some chains whose
  Naver name differs (e.g. BHC 낙성대점).
- Refresh it by running the command again with a newer CSV; do not edit it by hand.
