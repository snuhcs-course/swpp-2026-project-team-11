# Feature extraction: human review (i3-P21)

People judged, value by value, whether the LLM's extracted features are reasonable: for
each dish, every one of the 32 means and 32 stds is marked X (wrong) or left blank
(reasonable). The protocol, the pass bar and the commands are in
[backend/README.md](../../backend/README.md#human-review-of-the-extracted-features-p21);
the raters' steps (Korean) are in [docs/p21-human-evaluation.md](../../docs/p21-human-evaluation.md).

**Status (2026-11-06): interim.** 7 of 8 workbooks are in; `general_이민규.xlsx` is not.
[report.md](report.md) is the interim report and is regenerated when the last workbook
arrives.

## Files

| File | What |
|---|---|
| `cafeteria_<rater>.xlsx` | 2026-11-02 snapshot (`menus_2026-11-02` fixture), 20 dishes per rater |
| `general_<rater>.xlsx` | Restaurants near the stations, from the team's export `메추_음식별_feature_학식_일반_20261104.xlsx` (snapshot of 2026-11-03), 16-17 dishes per rater |
| `<source>_assignment.csv` | Every sampled dish: id, name, set, group, stratum (hard/other), hardness signals, rater |
| `report.md` | `report_feature_review` on all workbooks here |

The export workbook is not in the repository; its file name is recorded in the commits
that generated the general workbooks.

## Design

| | Cafeteria | General |
|---|---|---|
| Pool (dishes with v2 features) | 127 | 1,598 (6,226 menus grouped by linked dish and values) |
| Sample | 80 | 66 |
| Hard dishes (pool → sample) | 39 → 39 | 465 → 33 |
| Strata of the sample | by cafeteria | by restaurant category |
| Per rater | 20 (9-10 hard) | 16-17 (8-9 hard) |

- Raters: 구본재 (Bonjae Ku), 김신서 (Shinseo Kim), 이민규 (Mingyu Lee), 이승호 (Seungho Lee).
  Every rater has different dishes; there is no overlap, so rater agreement is not measured.
- Hard: two or more of four signals (a set; no cuisine or several at 0.3 or more; many
  means between 0.3 and 0.7; a large mean std). Half of each sample is hard; accuracy weights
  the hard and other dishes by their share of the pool. Raters were not told which dishes are hard.
- Pass, per source, for means and stds each: overall accuracy >= 95% and every feature >= 85%.
  Sampling seed 0.

### Revisions before the review

The plan was revised on 2026-11-05, before any workbook was handed out; the first ratings
came in on 2026-11-06.

| Version | Commit | Unit judged | Pass bar | Sample |
|---|---|---|---|---|
| 1 (original) | `a8050c9` | Dish: 합리적 / 일부 틀림 / 비합리적 / 판단 불가, plus the wrong keys | 합리적 >= 80% and 비합리적 <= 5% | Cafeteria 127 (all), general 100 from the mini PC database, 10 shared per source |
| 2 | `ab6cd1f` | Each mean and std (X / blank) | Overall >= 95%, every feature >= 85% | Cafeteria 127, general 100 from the export, proportional to restaurant category |
| 3 | `3baca1b` | same | same | Halved per rater: cafeteria 50, general 36 |
| 4 | `6cda8b4` | same | same | Half hard, strata weighted by pool share |
| 5 (used) | `64e1890` | same | same | No shared dishes: cafeteria 80, general 66, hard dishes split evenly |

Why: a dish verdict hid which values were wrong (v2); version 1's round-robin sample over
81 categories over-weighted small categories about 13 times (v2); the workload was too high
(v3); easy dishes dominate a random sample (v4); one dataset per rater (v5).

## Collection log

| Date | Rater | Cafeteria | General | Notes |
|---|---|---|---|---|
| 2026-11-06 | 김신서 | 20 done | 17 done | As filled |
| 2026-11-06 | 이승호 | 20 done | 16 done | As filled |
| 2026-11-06 | 이민규 | 20 done (converted) | not received | See below |
| 2026-11-06 | 구본재 | 20 done | 17 done | AI pre-filled, then checked; see below |

**이민규, cafeteria.** The rater overwrote the LLM's values with their own instead of marking X,
and left the status blank. On the collector's instruction, every value that differs from the
original workbook was marked X (34: 27 means, 7 stds), all 20 rows were set to 완료, the LLM's
values were restored, and the rater's values were written into the comment column
(`이민규 수정값: key old→new`). This counts changes smaller than the 0.3 rule as wrong.

**구본재, both workbooks.** At 구본재's request Claude (Claude Code) pre-filled both workbooks
(5 X: rice of 떡국 and 눈꽃치즈떡볶이; grilled of 스테이크샌드위치; large_portion of 농어회 (2인)
and 쟁반막국수 (특)). 구본재 then checked every row, kept all five marks unchanged and asked for
them to count as their ratings. They are reported as 구본재's, but started from an AI pre-fill,
so anchoring on the AI's marks is possible.

## Interim results (2026-11-06)

| Source | Raters | Dishes | Mean | Std | Lowest feature (mean) | Pass |
|---|---|---|---|---|---|---|
| Cafeteria | 4 | 80 | 98.2% | 99.4% | large_portion 82.7% | **no** |
| General | 3 | 50 | 98.1% | 98.6% | rice 90.3% | yes |

**Why the cafeteria fails: one feature, `large_portion`, at 82.7% against the 85% bar.** Every other feature and both overall accuracies pass.

- **One rater (이민규):** all 14 large_portion marks come from one rater, on 14 of their 20 dishes. The three other raters marked none.
- **Generous portions:** that rater judged portions larger than the LLM did, mostly fried chicken, tonkatsu, fried rice and noodle soups: 0.3–0.4 → 0.5–0.7.
- **Small gaps:** 8 of the 14 marks are below the 0.3 gap that defines a wrong mean (0.05–0.25). Counting only the 6 marks of 0.3 or more, large_portion is 93.5% and the cafeteria passes; the lowest feature is then greasy at 91.7%.
- **Underneath, the LLM barely varies `large_portion`:** 113 of the 127 cafeteria dishes (89%) get 0.3–0.4. So the feature says little, and its errors depend on how big a rater thinks a usual portion is. The rubric's reference portion is worth revisiting before the next extraction.

Other findings:

- Hard and other dishes score alike (cafeteria 98.2% and 98.2%; general 98.8% and 97.9%):
  the hardness signals did not pick out the values people call wrong.
- Below 95% on means: cafeteria large_portion, rice 90.9%, greasy 91.7%; general rice 90.3%,
  korean 93.2%, oily, pork and large_portion 94.3%.
- Raters differ a lot. X on means per 20 cafeteria dishes: 구본재 2, 이승호 3, 김신서 14, 이민규 27;
  per general workbook: 구본재 3, 이승호 6, 김신서 18. With no shared dishes this cannot be told
  apart from differences between their dishes.
