"""Read the .cypher scripts and split them into numbered steps for Exercise 2.

A step starts with a comment line '// STEP <n>: <title>'. Comment lines after it form the step's
description; statements end with ';'. Strings in the scripts never contain ';'.
"""
import os
import re

STEP_RE = re.compile(r"^//\s*STEP\s+(\d+)\s*:\s*(.+)$")


def statements(text):
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def parse_steps(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    steps, cur = [], None
    for ln in lines:
        m = STEP_RE.match(ln.strip())
        if m:
            cur = {"number": int(m.group(1)), "title": m.group(2).strip(), "description": [], "body": []}
            steps.append(cur)
            continue
        if cur is None:
            continue
        if ln.strip().startswith("//") and not cur["body"]:
            cur["description"].append(ln.strip().lstrip("/").strip())
        else:
            cur["body"].append(ln)
    for s in steps:
        text = "\n".join(s.pop("body"))
        s["statements"] = statements(text)
        s["cypher"] = ";\n\n".join(s["statements"]) + ";" if s["statements"] else ""
        s["description"] = " ".join(d for d in s["description"] if d)
    return steps


def script_path(scripts_dir, name):
    path = os.path.join(scripts_dir, name)
    if not os.path.exists(path):
        raise ValueError(f"Script {name} not found in {scripts_dir}.")
    return path
