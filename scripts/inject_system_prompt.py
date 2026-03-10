"""Inject a system prompt from a file into eval case JSON files."""
import json
import sys
from pathlib import Path

prompt_file = Path(sys.argv[1])
eval_dir = Path(sys.argv[2])

system_prompt = prompt_file.read_text()

for f in sorted(eval_dir.glob("*.json")):
    with open(f) as fh:
        case = json.load(fh)
    if "system_prompt" in case:
        case["system_prompt"] = system_prompt
        with open(f, "w") as fh:
            json.dump(case, fh, indent=2)
            fh.write("\n")
        print(f"  Updated: {f.name}")

print("Done.")
