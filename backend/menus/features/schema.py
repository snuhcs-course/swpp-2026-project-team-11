"""The food features the question engines work with - the single source of truth.

Each feature is a yes/no question the app can ask. A food's value for a feature is

    P(the user answers "yes" to that question | the food they want is this one)

in [0, 1], rounded to 0.1. MVP1 uses it directly as the likelihood in its Bayesian
update; 0.5 means "depends on how it's made" or "no idea".

Changing this list (keys, questions or meaning) means bumping FEATURE_VERSION, so
`extract_features` re-tags every food under the new schema.
"""

from __future__ import annotations

from dataclasses import dataclass

FEATURE_VERSION = "v1"


@dataclass(frozen=True)
class Feature:
    key: str
    question: str  # what the app asks the user
    guide: str     # what counts as "yes", for the LLM


FEATURES: tuple[Feature, ...] = (
    # 맛
    Feature("spicy", "매콤한 게 당겨요?", "고추·고추장·마라·청양고추 등으로 매운맛이 나는 음식"),
    Feature("sweet", "달달한 게 당겨요?", "양념이나 소스가 달거나 달콤한 맛이 두드러지는 음식"),
    Feature("sour_fresh", "새콤하거나 상큼한 게 당겨요?", "식초·과일·드레싱 등으로 새콤하거나 상큼한 음식"),
    Feature("greasy", "기름지고 느끼한 게 당겨요?", "튀김·크림·치즈·삼겹살처럼 기름지거나 느끼한 음식"),
    # 형태·온도
    Feature("soupy", "국물 있는 음식이 당겨요?", "국·탕·찌개·국물 요리처럼 국물이 중심인 음식"),
    Feature("hot", "뜨끈한 음식이 당겨요?", "뚝배기·국밥·찌개처럼 뜨겁게 먹는 음식"),
    Feature("cold", "시원하거나 차가운 음식이 당겨요?", "냉면·냉모밀·샐러드·포케처럼 차갑게 먹는 음식"),
    Feature("fried", "튀긴 음식이 당겨요?", "돈까스·치킨·튀김처럼 튀겨서 바삭한 음식"),
    Feature("grilled", "구이나 볶음, 불맛이 당겨요?", "구이·직화·철판·볶음 요리"),
    # 주식
    Feature("rice", "밥이 먹고 싶어요?", "덮밥·비빔밥·볶음밥·국밥·백반처럼 밥이 중심인 음식"),
    Feature("noodle", "면이 당겨요?", "국수·라면·우동·냉면·파스타·쌀국수 등 면 요리"),
    Feature("bread_flour", "빵이나 밀가루 음식이 당겨요?", "빵·버거·만두·전·베이크 등 밀가루 음식 (면 제외)"),
    # 단백질
    Feature("beef", "소고기가 당겨요?", "소고기가 주재료인 음식"),
    Feature("pork", "돼지고기가 당겨요?", "제육·삼겹살·돈까스처럼 돼지고기가 주재료인 음식"),
    Feature("chicken", "닭고기가 당겨요?", "치킨·닭갈비·찜닭처럼 닭고기가 주재료인 음식"),
    Feature("seafood", "해산물이나 생선이 당겨요?", "생선·새우·오징어·주꾸미·조개 등 해산물이 주재료인 음식"),
    Feature("meatless", "고기 없이 먹고 싶어요?", "고기가 없거나 거의 없는 음식 (두부·채소·해산물 위주 포함)"),
    # 무게감
    Feature("heavy", "배부르고 든든하게 먹고 싶어요?", "양이 많고 포만감이 큰 음식"),
    Feature("light_healthy", "가볍고 건강하게 먹고 싶어요?", "담백하고 칼로리가 낮거나 건강한 음식 (샐러드·포케·죽)"),
    # 국가
    Feature("korean", "한식이 당겨요?", "한국 음식"),
    Feature("chinese", "중식이 당겨요?", "짜장면·짬뽕·마라탕·탕수육 등 중국식 음식"),
    Feature("japanese", "일식이 당겨요?", "돈까스·우동·소바·덮밥(동)·카레 등 일본식 음식"),
    Feature("western_asian", "양식이나 동남아 음식이 당겨요?", "파스타·버거·스테이크·쌀국수 등 양식이나 동남아 음식"),
)

FEATURE_KEYS: tuple[str, ...] = tuple(f.key for f in FEATURES)
