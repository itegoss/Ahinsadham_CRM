import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = r"c:\Users\Varsha\Ahinsadham\Ahinsadham-main\heart_charity\templates\welcome.html"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "tab-content" in line or "class=\"tab-pane" in line or "role=\"tabpanel\"" in line:
        # Check if it has an id
        if "id=" in line:
            print(f"Line {idx+1}: {line.strip()}")
