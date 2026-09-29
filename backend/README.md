# Metchu! backend

Django 5.2 + SQLite server. For now it holds the MVP's candidate set: **the SNU cafeteria
dishes of a given day**, each tagged by an LLM with the features the question engines use.

- The local DB is **one file, `backend/db.sqlite3`**. It is gitignored, so everyone builds their own.
- Two ways to fill it:
  - **A. Load the shared snapshot**: no API key. Enough for engine development.
  - **B. Build any day yourself**: fetch that day's menu and tag it with Gemini using your own API key.

## 0. One-time setup

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate          # creates an empty db.sqlite3 (Restaurant / Food / MenuItem)
python manage.py test menus       # runs without an API key
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

`manage.py` loads it automatically (see `backend/env.py`).

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

### 2) Fetch the day's menu, then extract features

Today (Asia/Seoul):

```bash
python manage.py fetch_menus          # today's menu from Siksha -> DB (no key needed)
python manage.py extract_features     # tag new dishes with Gemini (key needed)
```

A specific day: pass the same `--date` to both. Siksha usually has the whole week's menu in advance.

```bash
python manage.py fetch_menus --date 2026-09-30
python manage.py extract_features --date 2026-09-30
```

- Try a small batch first: `python manage.py extract_features --limit 25 --dry-run` prints tags without saving.
- On days with no menu (weekends, holidays), `fetch_menus` prints `오늘 운영 메뉴 없음` and exits.
- `fetch_menus` is safe to re-run; it replaces that day's menu items.
- `extract_features` skips dishes that are already tagged. Use `--force` to re-tag them.

### 3) Cost and consistency

- The first day costs about 10 calls (~240 dishes in batches of 25, `gemini-3.5-flash`), a few hundred won.
- Dishes served every day (220동, the food court) are tagged once and reused. Later days only pay for new dishes.

> **주의:** LLM 결과는 실행할 때마다 조금씩 달라서, 각자 뽑은 feature 값이 서로 다를 수 있습니다.
> MVP1 vs MVP2 비교나 사용자 테스트처럼 **같은 조건이 필요한 경우에는 공유 스냅샷(방법 A)을 쓰세요.**

### 4) Inspect the result

```bash
python manage.py export_candidates --date 2026-09-30 --meal LU --output candidates.json
python manage.py createsuperuser && python manage.py runserver   # then http://127.0.0.1:8000/admin
```

To start over, delete `backend/db.sqlite3` and run `python manage.py migrate` again.

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
```

> **feature 값의 뜻:** "이 음식을 원하는 사람에게 그 질문을 하면 '예'라고 답할 확률" (0~1, 0.1 단위).
> MVP1은 Bayesian update의 likelihood로 바로 쓰고, MVP2는 `display_name` 목록만 LLM에 넘기면 됩니다.

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
| `fetch_menus [--date]` | fetch and store a day's menu | no |
| `extract_features [--date] [--limit N] [--dry-run] [--force]` | tag new dishes with features | **yes** |
| `export_candidates [--date] [--meal] [--output]` | candidates + feature schema as JSON | no |

## Data model (`menus/models.py`)

| Model | One row per | Notes |
|---|---|---|
| `Restaurant` | cafeteria | `code` is the Siksha id, e.g. `220동식당` |
| `Food` | distinct dish | the unit that gets recommended; holds `features`, `is_food`, `display_name`, `food_group` |
| `MenuItem` | dish x restaurant x meal x day | `meal` is `BR` / `LU` / `DN`; `price` in won |

## Data source

Menus come from the public [Siksha](https://siksha.wafflestudio.com) API by Waffle Studio.

- Endpoint: `https://siksha-api.wafflestudio.com/menus/?start_date=...&end_date=...`
- One request per run.
- The official SNU co-op page (`https://snuco.snu.ac.kr/foodmenu/`) is the planned fallback.
