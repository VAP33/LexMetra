import json

def deterministic_json_parse(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        idx = raw.rfind("},")
        if idx != -1:
            candidate = raw[:idx+1] + "\n  ]\n}"
            try:
                return json.loads(candidate)
            except Exception:
                pass
        idx = raw.rfind("}")
        if idx != -1:
            candidate = raw[:idx+1] + "\n  ]\n}"
            try:
                return json.loads(candidate)
            except Exception:
                pass
        raise

with open(r"c:\Users\HP\SIH LATEST\backend\traya_qwen_clean.json", "r", encoding="utf-8") as f:
    text = f.read()

parsed = deterministic_json_parse(text)
print("Parsed successfully!")
print(f"Product: {parsed.get('product_name')}")
print(f"Product ID: {parsed.get('product_id')}")
for d in parsed.get("declarations", []):
    print(f"  {d.get('field')}: {d.get('value')}")
