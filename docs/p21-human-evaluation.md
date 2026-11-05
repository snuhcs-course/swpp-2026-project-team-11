# P21 사람 평가 안내

LLM 가상 사용자로만 돌렸던 평가를 사람이 같은 조건으로 합니다.

| 누가 | 할 일 | 제출 |
|---|---|---|
| 테스터 4명 (구본재, 김신서, 이민규, 이승호) | 1부 추천 평가 → 2부 feature 검토 | `.jsonl` 1개, `.xlsx` 2개 → 구본재 |
| 미니 PC 담당자 | 일반 음식점 검토 파일 내보내기 (지금) | 파일 5개와 출력 → 구본재 |
| 구본재 | 수합, 커밋, 보고서 | - |

- 마감: 2026-11-06
- 설계와 통과 기준: [벤치마크 README](../backend/question_engines/benchmark/README.md#user-study-p21), [backend README](../backend/README.md#human-review-of-the-extracted-features-p21)

---

## 테스터

> **순서: 1부(추천) → 2부(feature).** feature 값을 먼저 보면 질문에 답하는 방식이 달라질 수 있습니다.
> 아래 `이름`은 모든 명령과 파일에서 위 표의 이름 그대로 씁니다.

### 0. 준비 (처음 한 번)

PR이 머지되기 전에는 브랜치에서, 머지된 뒤에는 `main`에서 합니다.

```bash
git fetch origin && git switch feat/i3-p21-human-eval
cd backend
pip install -r requirements.txt
export DATABASE_URL=sqlite:///p21.sqlite3     # 평가 전용 로컬 DB
python manage.py migrate
python manage.py loaddata menus_2026-11-02
```

- PowerShell이면 `export X=값` 대신 `$env:X = "값"`을 씁니다.
- **새 터미널을 열 때마다 `DATABASE_URL`을 다시 설정하세요.** 빠지면 `.env`에 적힌 공유 DB에 연결될 수 있습니다.
- 저장소 루트 `.env`에 `OPENROUTER_API_KEY`가 있어야 합니다. 없으면 라운드를 시작하기 전에 오류로 멈춥니다.
  LLM 엔진 세션 하나에 약 $0.01~0.02(팀 키)가 듭니다.

### 1부. 추천 평가: 4라운드, 세션 12개, 약 30~40분

`backend/`에서 실행합니다.

```bash
export DATABASE_URL=sqlite:///p21.sqlite3 METCHU_MAX_QUESTIONS=20
R=../engine_benchmark_results/2026-11-02
python manage.py play_engine_session --scenarios $R/scenarios.json --tester 이름 \
    --output $R/9_user_study/human/이름.jsonl
```

한 번 실행하면 한 라운드를 합니다. `이름: 4라운드를 모두 마쳤습니다`가 나올 때까지 **같은 명령을 4번** 실행합니다.

#### 한 라운드의 흐름

**① 먹고 싶은 것 고르기.** 메뉴 목록이 나오고, 안내 문구가 무엇을 고를지 알려 줍니다.

| 안내 문구 | 입력 |
|---|---|
| 메뉴 하나의 번호 | 지금 가장 먹고 싶은 메뉴 번호 하나 (`12`) |
| 서로 다른 메뉴 2~3개의 번호 | 똑같이 좋은 메뉴 번호를 쉼표로 (`3,17`) |
| 오늘 메뉴에 없는 음식 이름 | 먹고 싶은데 목록에 없는 음식 이름 (`마라탕`). 비슷한 메뉴가 있으면 다시 묻습니다 |
| `~ 비슷한 메뉴`가 붙은 목록 | 그중 번호 하나. 이 라운드는 **고른 그 메뉴만** 정답입니다 |

실제로 먹을 것을 고르세요. 앱이 맞히기 쉬울지 어려울지는 생각하지 않습니다.

**② 확실도.** 먹고 싶은 것이 얼마나 확실한지 솔직하게 고릅니다.
`1` 확실하다, `2` 대체로, `3` 애매하다.

**③ 세션 3개.** 같은 소원으로 엔진 3개를 차례로 합니다. 어떤 엔진인지는 표시되지 않습니다.

- 질문에는 **번호로** 답합니다.
- 판단이 안 되면 `잘 모르겠어요`, 아무래도 좋으면 `상관없어요`를 고릅니다.
- **세션마다 처음인 것처럼** 답합니다. 앞 세션의 질문이나 제안은 잊으세요.
- 앱을 원하는 쪽으로 유도하지 않습니다.

**④ 제안 판정.**

- 내가 고른 메뉴가 제안되면 자동으로 수락됩니다.
- `비슷한 메뉴` 라운드에서는 고른 메뉴가 아닌 제안이 자동으로 거절됩니다.
- 그 밖의 제안에는 `y`/`n`으로 답합니다.

| 상황 | `y`로 답하는 경우 | 예 |
|---|---|---|
| 고른 메뉴가 오늘 있음 | 사실상 같은 음식 (같은 종류, 같은 주재료) | 햄버거 대신 치즈버거 `y`, 갈비 `n` |
| 고른 음식이 오늘 없음 | 같은 욕구를 채워 줌 | 생선가스 대신 돈가스 `y`, 짜장면 `n` |

맛있어 보이거나 든든하다는 이유만으로는 `y`를 하지 않습니다. 5번 거절하면 그 세션이 끝납니다.

**⑤ 만족도.** 세션이 끝날 때마다 1~5점을 줍니다. 그 세션의 결과와 걸린 수고를 합쳐 얼마나 만족했는지입니다.

#### 중간에 끊겼을 때

Ctrl-C로 멈췄거나 네트워크 오류가 났으면 **같은 명령을 다시 실행**합니다.

- 같은 소원으로 그 라운드를 이어서 합니다.
- 오류로 끝난 세션은 다시 합니다.
- `.jsonl` 파일은 고치거나 지우지 않습니다.

#### 제출

`engine_benchmark_results/2026-11-02/9_user_study/human/이름.jsonl` → 구본재

### 2부. feature 검토: 학식 약 40분 + 일반 음식점 약 35분

LLM이 음식 이름만 보고 뽑은 32개 feature가 그 음식에 맞는지 판단합니다. 값을 새로 매기는 것이 아닙니다.

**파일** (`feature_benchmark_results/2026-11-02-review/`)

- `cafeteria_이름.xlsx`: 학식 39~40개, 지금 있음
- `general_이름.xlsx`: 일반 음식점 32~33개, 미니 PC에서 받는 대로 구본재가 올립니다

**보는 법**

- 한 행이 음식 하나입니다.
- `분류`, `세트`, `판매 예`(식당과 실제 메뉴 줄)로 어떤 음식인지 확인합니다.
- feature마다 두 칸입니다. 왼쪽 mean은 그 특징이 얼마나 두드러지는지(0~1, 진할수록 높음)입니다. 오른쪽 std는 레시피나 식당에 따라 얼마나 다른지입니다.
- 판단 기준은 `루브릭` 시트, 작성 방법은 `안내` 시트, 내 판정 집계는 `요약` 시트에 있습니다.

**노란 칸만 채웁니다**

| 열 | 입력 |
|---|---|
| B `판정` | 목록에서 선택: `합리적` 틀린 feature 없음 / `일부 틀림` 1~3개 / `비합리적` 4개 이상, 또는 다른 음식으로 이해함 / `판단 불가` 레시피와 사진을 찾아봐도 모르는 음식 |
| C `틀린 feature` | 4행의 key를 쉼표로 (`spicy, soupy`). `일부 틀림`이면 필수 (비어 있으면 빨갛게 표시) |
| D `의견` | 어떻게 틀렸는지 짧게 (`spicy 0.1 → 0.7`) |

**틀렸다고 보는 기준**

- mean이 루브릭으로 보아 **0.3 이상** 어긋남 (예: 짬뽕 spicy 0.10)
- std가 레시피 차이와 분명히 맞지 않음 (예: 식당마다 크게 다른 음식인데 std 0)
- 그보다 작은 차이는 틀린 것으로 보지 않습니다.

**주의**

- 혼자 판단합니다. 다른 사람과 상의하지 않습니다.
- 행 순서, 다른 칸, 시트 이름은 바꾸지 않습니다.
- 같은 이름의 `.xlsx`로 저장합니다. Google Sheets에서 했다면 `.xlsx`로 내려받습니다.

**제출:** 두 파일 → 구본재

---

## 미니 PC 담당자: 지금 할 일

일반 음식점 feature는 미니 PC DB에만 있습니다. **DB 사본에서 읽기만** 해서 검토 파일을 만듭니다.

> **하지 말 것:** `private/menu.sqlite3`, `release.txt`, `releases/`, `daily_menus.py`, Windows 작업은 건드리지 않습니다.
> 호스트를 멈추거나 재시작하지 않습니다. 커밋, 푸시, PR도 하지 않습니다.

**1. 소스 받기.** 아래 파일을 `%TEMP%\p21-review\src`에 풀어 둡니다. `releases/`에는 두지 않습니다.
<https://github.com/snuhcs-course/swpp-2026-project-team-11/archive/refs/heads/feat/i3-p21-human-eval.zip>

**2. DB 사본 만들고 사본만 쓰도록 설정** (PowerShell)

```powershell
$py = "$env:LOCALAPPDATA\MetchuHost\venv\Scripts\python.exe"
New-Item -ItemType Directory -Force "$env:TEMP\p21-review" | Out-Null
& $py -c "import sqlite3,os; s=sqlite3.connect(os.path.expandvars(r'%LOCALAPPDATA%\MetchuHost\private\menu.sqlite3')); d=sqlite3.connect(os.path.expandvars(r'%TEMP%\p21-review\menu-copy.sqlite3')); s.backup(d); d.close(); s.close()"
$env:DATABASE_URL = "sqlite:///" + ("$env:TEMP\p21-review\menu-copy.sqlite3" -replace '\\','/')
$env:GOOGLE_API_KEY = "x-unused"; $env:OPENROUTER_API_KEY = "x-unused"; $env:OPENAI_API_KEY = "x-unused"
cd "$env:TEMP\p21-review\src\swpp-2026-project-team-11-feat-i3-p21-human-eval\backend"
& $py manage.py showmigrations menus
```

- SQLite 백업 API는 호스트가 켜져 있어도 안전합니다.
- 키에 넣는 가짜 값은 `.env`의 진짜 키가 읽히지 않게 하려는 것입니다. PowerShell은 빈 값을 넣으면 변수를 지웁니다. 이 단계에서 모델을 호출하는 명령은 없습니다.
- `showmigrations`에 `[ ]`(미적용)가 있으면 `& $py manage.py migrate`를 실행합니다. 사본에만 적용됩니다.

**3. 내보내기**

```powershell
& $py manage.py export_feature_review --stores --n 100 --raters 구본재,김신서,이민규,이승호 --output-dir "$env:TEMP\p21-review\out"
& $py manage.py shell -c "from menus.models import StoreMenu, Food; print(StoreMenu.objects.count(), Food.objects.filter(store_menus__isnull=False, feature_version='v2', is_food=True).distinct().count())"
```

첫 명령은 다음 한 줄을 출력해야 합니다. seed가 고정이라 같은 DB에서는 같은 표본이 나옵니다.

```
general: 음식 100개 (공통 10개), 검토자별 구본재 33, 김신서 33, 이민규 32, 이승호 32 -> ...
```

**4. 구본재에게 보낼 것**

- `%TEMP%\p21-review\out`의 파일 5개:
  `general_구본재.xlsx`, `general_김신서.xlsx`, `general_이민규.xlsx`, `general_이승호.xlsx`, `general_assignment.csv`(음식 100행)
- 3단계 첫 명령의 출력 한 줄
- `shell -c`가 출력한 숫자 두 개
- DB 사본을 만든 시각

보낸 뒤 `menu-copy.sqlite3`를 지웁니다. 어느 단계든 실패하면(열이 없음, 음식이 100개보다 적음 등) 거기서 멈추고 오류 출력을 그대로 보냅니다. 실제 DB에서 우회하지 않습니다.

---

## 수합 (구본재)

**1. 받은 파일을 PR 브랜치에 커밋합니다.**

| 파일 | 위치 |
|---|---|
| `general_*.xlsx`, `general_assignment.csv` | `feature_benchmark_results/2026-11-02-review/` (올린 뒤 검토자들에게 알림) |
| 테스터의 `이름.jsonl` | `engine_benchmark_results/2026-11-02/9_user_study/human/` |
| 채운 검토 파일 | 빈 파일 자리에 덮어쓰기 |

**2. 보고서를 만듭니다** (모델 호출 없음)

```bash
cd backend
R=../engine_benchmark_results/2026-11-02
python manage.py benchmark_engines --scenarios $R/scenarios.json --human $R/9_user_study/human/*.jsonl --output-dir $R
F=../feature_benchmark_results/2026-11-02-review
python manage.py report_feature_review --reviews $F/*.xlsx --output $F/report.md
```

**3. (선택) 가상 사용자와 사람을 비교합니다.** 가상 사용자 모델을 호출하는 유료 실행입니다.

```bash
python manage.py validate_simulator --human $R/9_user_study/human/*.jsonl --output $R/9_user_study/simulator_check.jsonl --dry-run
```

1. `--dry-run`으로 호출 수를 확인합니다.
2. 같은 명령을 `--dry-run` 없이 실행합니다.
3. 2단계의 `benchmark_engines`에 `--simulator-check $R/9_user_study/simulator_check.jsonl`을 붙여 다시 실행합니다.

**4. 일정표 행과 Testing Documentation 위키에 결과를 올립니다.**
