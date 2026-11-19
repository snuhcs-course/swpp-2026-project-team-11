"""User-authored extraction rubric; only the API envelope differs from the CSV task."""
import json
from pathlib import Path
from .schema import LLM_FEATURE_KEYS, RUBRIC
PROMPT_VERSION = RUBRIC["prompt_version"]
_INSTRUCTIONS = Path(__file__).with_name("instructions.txt").read_text().strip()

def build_system_prompt(feature_order=LLM_FEATURE_KEYS):
    if sorted(feature_order) != sorted(LLM_FEATURE_KEYS):
        raise ValueError("feature_order must list every feature once")
    order = "출력 feature key 순서\n" + ", ".join(feature_order) + "\n" + "\n".join("| " + key for key in feature_order) + "\n"
    return _INSTRUCTIONS + order + "\n\n전송 형식만 JSON으로 바꾼다. 위 CSV 출력 지시 대신 items 배열을 출력한다. 각 항목은 입력 input_name과 features를 포함한다. features에는 53개 한국어 이름을 key로 사용하고 각 값은 mean, std, mask 객체다. mask=false일 때 mean/std는 null이다. 음식 의미와 점수 기준은 위 원문 그대로 따른다.\n" + json.dumps({f["label_ko"]:f["key"] for f in RUBRIC["features"]},ensure_ascii=False)
SYSTEM_PROMPT = build_system_prompt()
def build_user_message(names):
    return json.dumps({"items":[{"food_id":str(i),"name":name,"input_name":name} for i,name in enumerate(names)]},ensure_ascii=False)
