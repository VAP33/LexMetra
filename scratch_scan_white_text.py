import re
from pathlib import Path

COMPONENTS_DIR = Path(r"c:\Users\HP\SIH LATEST\frontend\react-app\src\components")

for file_path in COMPONENTS_DIR.glob("*.tsx"):
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    for idx, line in enumerate(lines, 1):
        # Look for text-white or text-background
        if "text-white" in line or "text-background" in line or "text-slate-50" in line:
            # Check if this line or context has dark background
            print(f"[{file_path.name}:{idx}] {line.strip()[:140]}")
