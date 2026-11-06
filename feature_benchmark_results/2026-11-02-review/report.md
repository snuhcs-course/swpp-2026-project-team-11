# Feature extraction: human review

Accuracy: the share of values judged reasonable on completed rows, the hard and other dishes weighted by their share of the pool (hard dishes are half of each sample). Pass, per source and for means and stds each: overall >= 95% and every feature >= 85% (fixed before the review). A mean is wrong when it is 0.3 or more off the rubric; a std when it plainly contradicts the recipe spread. Agreement: the share of values two raters of a shared dish judged alike; X agreement: the same among values either of them marked X.

| source | raters | dishes | completed | unknown | mean | worst mean | std | worst std | pass | agreement (shared dishes) | X agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cafeteria 2026-11-02 | 4 | 80 | 80 | 0 | 98.2% | large_portion 82.7% | 99.4% | rice 93.4% | no | - | - |
| general | 3 | 50 | 50 | 0 | 98.1% | rice 90.3% | 98.6% | rice 90.3% | yes | - | - |

**By stratum** (hard: 2+ signals, half of each sample; accuracy unweighted)

| source | stratum | pool | completed | mean | std |
|---|---|---|---|---|---|
| cafeteria 2026-11-02 | hard | 39 | 39 | 98.2% | 99.2% |
| cafeteria 2026-11-02 | other | 88 | 41 | 98.2% | 99.5% |
| general | hard | 465 | 25 | 98.8% | 99.0% |
| general | other | 1133 | 25 | 97.9% | 98.5% |

**Accuracy per feature, cafeteria 2026-11-02**

| key | 이름 | mean | std |
|---|---|---|---|
| spicy | 매운맛 | 100.0% | 99.2% |
| sweet | 단맛 | 98.3% | 99.2% |
| sour | 신맛 | 98.3% | 98.3% |
| oily | 기름기 | 100.0% | 100.0% |
| greasy | 느끼함 | 91.7% | 98.3% |
| smoky | 불향 | 98.3% | 100.0% |
| crispy | 바삭함 | 95.8% | 97.5% |
| soupy | 국물 있음 | 100.0% | 100.0% |
| hot | 뜨거움 | 98.3% | 100.0% |
| cold | 차가움 | 100.0% | 100.0% |
| fried | 튀김 | 98.3% | 98.3% |
| grilled | 구이 | 100.0% | 100.0% |
| stir_fried | 볶음 | 100.0% | 100.0% |
| rice | 밥 중심 | 90.9% | 93.4% |
| noodle | 면 중심 | 100.0% | 100.0% |
| bread | 빵 중심 | 100.0% | 100.0% |
| wheat | 밀 | 98.4% | 98.4% |
| beef | 소고기 | 100.0% | 100.0% |
| pork | 돼지고기 | 98.4% | 98.4% |
| chicken | 닭고기 | 100.0% | 100.0% |
| fish | 생선 | 97.5% | 99.2% |
| crustacean | 갑각류 | 99.2% | 100.0% |
| bivalve | 이매패류 | 99.2% | 100.0% |
| cephalopod | 두족류 | 100.0% | 100.0% |
| large_portion | 양이 많음 | 82.7% | 100.0% |
| filling | 포만감 | 98.3% | 100.0% |
| korean | 한식 | 98.4% | 100.0% |
| chinese | 중식 | 100.0% | 100.0% |
| japanese | 일식 | 100.0% | 100.0% |
| western | 양식 | 100.0% | 100.0% |
| southeast_asian | 동남아식 | 100.0% | 100.0% |
| indian | 인도식 | 100.0% | 100.0% |

**Accuracy per feature, general**

| key | 이름 | mean | std |
|---|---|---|---|
| spicy | 매운맛 | 96.0% | 93.2% |
| sweet | 단맛 | 100.0% | 100.0% |
| sour | 신맛 | 97.2% | 97.2% |
| oily | 기름기 | 94.3% | 97.2% |
| greasy | 느끼함 | 96.0% | 97.2% |
| smoky | 불향 | 96.0% | 93.2% |
| crispy | 바삭함 | 98.8% | 100.0% |
| soupy | 국물 있음 | 100.0% | 100.0% |
| hot | 뜨거움 | 100.0% | 100.0% |
| cold | 차가움 | 97.2% | 97.2% |
| fried | 튀김 | 100.0% | 100.0% |
| grilled | 구이 | 97.2% | 100.0% |
| stir_fried | 볶음 | 100.0% | 100.0% |
| rice | 밥 중심 | 90.3% | 90.3% |
| noodle | 면 중심 | 100.0% | 100.0% |
| bread | 빵 중심 | 100.0% | 100.0% |
| wheat | 밀 | 97.7% | 97.7% |
| beef | 소고기 | 100.0% | 100.0% |
| pork | 돼지고기 | 94.3% | 97.2% |
| chicken | 닭고기 | 100.0% | 100.0% |
| fish | 생선 | 98.8% | 98.8% |
| crustacean | 갑각류 | 100.0% | 100.0% |
| bivalve | 이매패류 | 100.0% | 100.0% |
| cephalopod | 두족류 | 100.0% | 100.0% |
| large_portion | 양이 많음 | 94.3% | 100.0% |
| filling | 포만감 | 100.0% | 100.0% |
| korean | 한식 | 93.2% | 98.8% |
| chinese | 중식 | 100.0% | 100.0% |
| japanese | 일식 | 100.0% | 100.0% |
| western | 양식 | 100.0% | 100.0% |
| southeast_asian | 동남아식 | 98.8% | 98.8% |
| indian | 인도식 | 100.0% | 100.0% |
