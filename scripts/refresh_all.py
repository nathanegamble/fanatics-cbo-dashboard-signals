#!/usr/bin/env python3
"""Run all refreshers, validate JSON, and update manifest."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def run(script: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, text=True, capture_output=True, timeout=180)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def main() -> int:
    DATA.mkdir(exist_ok=True)
    results = {}
    exit_code = 0
    for script in ["refresh_api_sports.py", "refresh_events.py"]:
        code, output = run(script)
        results[script] = {"exit_code": code, "output": output[-2000:]}
        if code != 0:
            exit_code = code
    facts = load("sports-facts.json")
    events = load("sports-events.json")
    raw_base = "https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data"
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if facts.get("status") in {"ok", "partial"} and events.get("status") in {"ok", "partial"} else "error",
        "version": "0.1",
        "files": {
            "sports_facts": {"path": "data/sports-facts.json", "raw_url": f"{raw_base}/sports-facts.json", "status": facts.get("status"), "as_of": facts.get("as_of")},
            "sports_events": {"path": "data/sports-events.json", "raw_url": f"{raw_base}/sports-events.json", "status": events.get("status"), "as_of": events.get("as_of")},
        },
        "run_results": results,
        "consumer_notes": [
            "sports-facts.json includes derived season_phase plus phase_detail, phase_basis, and phase_confidence.",
            "sports-events.json keeps Cowork's window concept but nests each window as {window_start, window_end, items} for date clarity.",
            "All committed outputs are public sports facts/news references; no API keys or credentials are written.",
        ],
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "files": manifest["files"]}, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
