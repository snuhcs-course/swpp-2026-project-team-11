# Metchu! backend

Django 5.2 + SQLite. For now it holds the MVP's candidate set: today's SNU
cafeteria dishes, each tagged by an LLM with the features the question engines use.

## Setup

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env        # then put your GOOGLE_API_KEY in it (server only)
python manage.py migrate
python manage.py test menus       # no API key needed
```

## Daily pipeline (all default to today in Asia/Seoul)

```bash
python manage.py fetch_menus          # 1. today's menus -> Restaurant / MenuItem / Food
python manage.py extract_features     # 2. tag new dishes with Gemini (needs GOOGLE_API_KEY)
python manage.py export_candidates --meal LU --output candidates.json   # 3. optional JSON dump
```

- `fetch_menus [--date YYYY-MM-DD]`: re-running replaces that day's menu items.
- `extract_features [--date] [--limit N] [--dry-run] [--force]`: only dishes not yet tagged
  under the current `FEATURE_VERSION` are sent to the LLM. `--dry-run --limit 25` prints
  the tags without saving, for a quick check.
- No API key? Load the shared snapshot instead (2026-09-29, 208 tagged dishes):
  `python manage.py migrate && python manage.py loaddata menus_2026-09-29`, then use
  `--date 2026-09-29` / `services.get_candidates(datetime.date(2026, 9, 29))`.

## Data model (`menus/models.py`)

| Model | One row per | Notes |
|---|---|---|
| `Restaurant` | cafeteria | `code` is the Siksha id, e.g. `220동식당` |
| `Food` | distinct dish | the unit that gets recommended; holds `features`, `is_food`, `display_name`, `food_group` |
| `MenuItem` | dish x restaurant x meal x day | `meal` is `BR` / `LU` / `DN`; `price` in won |

## For the question engines (`menus/services.py`)

```python
from menus import services

services.get_feature_schema()   # [{"key": "spicy", "question": "매콤한 게 당겨요?"}, ...]
services.get_candidates()       # today, all meals
services.get_candidates(meal="LU")
# [{"food_id", "name", "display_name", "food_group",
#   "features": {"spicy": 0.9, ...}, "offers": [{"restaurant", "meal", "price"}]}, ...]
```

A feature value is **P(the user answers "yes" to that feature's question | they want
this dish)**, in [0, 1] rounded to 0.1, so MVP1 can use it directly as the likelihood
in its Bayesian update. The feature list lives in `menus/features/schema.py`; changing
it means bumping `FEATURE_VERSION` and re-running `extract_features`.

## Data source

Menus come from the public [Siksha](https://siksha.wafflestudio.com) API by Waffle Studio
(`https://siksha-api.wafflestudio.com/menus/?start_date=...&end_date=...`), one request
per run. The official SNU co-op page (`https://snuco.snu.ac.kr/foodmenu/`) is the
planned fallback.
