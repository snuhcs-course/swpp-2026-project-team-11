# Feature extraction: human review

Accuracy: the share of values judged reasonable on completed rows, the hard and other dishes weighted by their share of the pool (hard dishes are half of each sample). Pass, per source and for means and stds each: overall >= 95% and every feature >= 85% (fixed before the review); incomplete while a stratum of the pool has no completed row. A mean is wrong when it is 0.3 or more off the rubric; a std when it plainly contradicts the recipe spread. Agreement: the share of values two raters of a shared dish judged alike; X agreement: the same among values either of them marked X.

| source | raters | dishes | completed | unknown | mean | worst mean | std | worst std | pass | agreement (shared dishes) | X agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cafeteria 2026-11-02 | 4 | 80 | 80 | 0 | 98.2% | large_portion 82.7% | 99.4% | rice 93.4% | no | - | - |
| general | 4 | 66 | 66 | 0 | 98.2% | large_portion 90.5% | 98.9% | rice 92.7% | yes | - | - |

**By stratum** (hard: 2+ signals, half of each sample; accuracy unweighted)

| source | stratum | pool | completed | mean | std |
|---|---|---|---|---|---|
| cafeteria 2026-11-02 | hard | 39 | 39 | 98.2% | 99.2% |
| cafeteria 2026-11-02 | other | 88 | 41 | 98.2% | 99.5% |
| general | hard | 465 | 33 | 98.5% | 99.1% |
| general | other | 1133 | 33 | 98.1% | 98.9% |

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
| spicy | 매운맛 | 96.1% | 94.8% |
| sweet | 단맛 | 100.0% | 100.0% |
| sour | 신맛 | 97.9% | 97.9% |
| oily | 기름기 | 95.7% | 97.9% |
| greasy | 느끼함 | 97.0% | 97.9% |
| smoky | 불향 | 97.0% | 94.8% |
| crispy | 바삭함 | 99.1% | 100.0% |
| soupy | 국물 있음 | 100.0% | 100.0% |
| hot | 뜨거움 | 100.0% | 100.0% |
| cold | 차가움 | 97.9% | 97.9% |
| fried | 튀김 | 100.0% | 100.0% |
| grilled | 구이 | 97.9% | 100.0% |
| stir_fried | 볶음 | 100.0% | 100.0% |
| rice | 밥 중심 | 92.7% | 92.7% |
| noodle | 면 중심 | 100.0% | 100.0% |
| bread | 빵 중심 | 100.0% | 100.0% |
| wheat | 밀 | 97.4% | 98.2% |
| beef | 소고기 | 100.0% | 100.0% |
| pork | 돼지고기 | 95.7% | 97.9% |
| chicken | 닭고기 | 100.0% | 100.0% |
| fish | 생선 | 99.1% | 99.1% |
| crustacean | 갑각류 | 100.0% | 100.0% |
| bivalve | 이매패류 | 100.0% | 100.0% |
| cephalopod | 두족류 | 100.0% | 100.0% |
| large_portion | 양이 많음 | 90.5% | 100.0% |
| filling | 포만감 | 97.0% | 100.0% |
| korean | 한식 | 93.9% | 98.2% |
| chinese | 중식 | 100.0% | 100.0% |
| japanese | 일식 | 99.1% | 100.0% |
| western | 양식 | 100.0% | 100.0% |
| southeast_asian | 동남아식 | 99.1% | 99.1% |
| indian | 인도식 | 100.0% | 100.0% |
