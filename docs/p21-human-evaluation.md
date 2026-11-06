# P21 사람 평가 안내

LLM 가상 사용자로만 돌렸던 평가를 사람이 같은 조건으로 합니다.

> **Iteration 3에서는 2부(feature 검토)만 합니다.** 1부(추천 평가)는 Iteration 4로 미뤘습니다. 이미 한 세션 기록은 그대로 둡니다.

| 누가 | 할 일 | 제출 |
|---|---|---|
| 테스터 4명 (구본재, 김신서, 이민규, 이승호) | 1부 추천 평가 → 2부 feature 검토 | `.jsonl` 1개, `.xlsx` 2개 → 구본재 |
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

### 2부. feature 검토: 학식 약 35분 + 일반 음식점 약 30분

LLM이 음식 이름만 보고 뽑은 32개 feature의 mean과 std가 그 음식에 맞는지 **값 하나하나** 판단합니다. 값을 새로 매기는 것이 아닙니다.

**파일** (`feature_benchmark_results/2026-11-02-review/`)

- `cafeteria_이름.xlsx`: 학식 20개
- `general_이름.xlsx`: 일반 음식점 16~17개

**보는 법**

- 한 행이 음식 하나입니다. `분류`, `세트`, `판매 예`(그 음식으로 연결된 실제 메뉴, 최대 3개)로 어떤 음식인지 확인합니다.
- feature마다 네 칸입니다: mean 값, mean 판정, std 값, std 판정. mean은 그 특징이 얼마나 두드러지는지(0~1, 진할수록 높음), std는 레시피나 식당에 따라 얼마나 다른지입니다.
- 판단 기준은 `루브릭` 시트, 작성 방법은 `안내` 시트, 내 feature별 정확도는 `요약` 시트에 있습니다.

**노란 칸만 채웁니다**

| 칸 | 입력 |
|---|---|
| 값 오른쪽 판정 칸 (`..._wrong`) | 틀린 값이면 `X`, 맞으면 **비워 둡니다** (X는 빨갛게 표시) |
| C `상태` | 한 행의 64개 값을 다 봤으면 `완료`. 레시피와 사진을 찾아봐도 모르는 음식이면 `판단 불가` |
| G `의견` | 선택. 눈에 띄게 틀린 값을 짧게 (`spicy 0.1 → 0.7`) |

- **상태가 빈 행은 집계되지 않습니다.** X를 넣고 상태를 비워 두면 상태 칸이 빨갛게 표시됩니다.
- 한 행씩: 음식 확인 → 값 64개를 보며 틀린 곳에 X → `완료`.

**틀렸다고 보는 기준**

- mean: 루브릭으로 보아 **0.3 이상** 어긋남 (예: 짬뽕 spicy 0.10). 그보다 작은 차이는 맞는 것으로 봅니다.
- std: 레시피·식당에 따른 차이와 분명히 맞지 않음 (예: 식당마다 크게 다른 음식인데 std 0, 어디서나 같은 특징인데 std가 큼).

**주의**

- 혼자 판단합니다. 다른 사람과 상의하지 않습니다.
- 행 순서, 다른 칸, 시트 이름은 바꾸지 않습니다.
- 같은 이름의 `.xlsx`로 저장합니다. Google Sheets에서 했다면 `.xlsx`로 내려받습니다.

**제출:** 두 파일 → 구본재

---

## 수합 (구본재)

**1. 받은 파일을 PR 브랜치에 커밋합니다.**

| 파일 | 위치 |
|---|---|
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
