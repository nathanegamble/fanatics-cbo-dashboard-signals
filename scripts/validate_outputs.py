#!/usr/bin/env python3
"""Basic validation for public JSON outputs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SECRET_PATTERNS = [
    re.compile(r"[a-f0-9]{32,}", re.I),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"API[_-]?KEY", re.I),
]
ALLOWLIST = {"raw.githubusercontent.com"}


def assert_no_obvious_secret(path: Path) -> None:
    text = path.read_text()
    for pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            value = m.group(0)
            if "api-sports" in value.lower():
                continue
            raise AssertionError(f"Possible secret-like value in {path}: {value[:8]}…")


def validate_facts(obj: dict) -> None:
    for key in ["generated_at", "as_of", "status", "warnings", "leagues"]:
        assert key in obj, f"sports-facts missing {key}"
    assert isinstance(obj["leagues"], list) and obj["leagues"], "sports-facts leagues empty"
    allowed = {"in-season", "pre-season", "post-season", "off-season", "unknown"}
    for league in obj["leagues"]:
        assert league.get("season_phase") in allowed, f"bad season_phase: {league}"
        assert "phase_basis" in league and "phase_confidence" in league, f"missing phase explanation: {league.get('league')}"


def validate_events(obj: dict) -> None:
    for key in ["generated_at", "as_of", "status", "warnings", "windows"]:
        assert key in obj, f"sports-events missing {key}"
    for name in ["yesterday", "today", "this_week", "this_month", "next_month"]:
        assert name in obj["windows"], f"missing window {name}"
        win = obj["windows"][name]
        assert "window_start" in win and "window_end" in win and "items" in win, f"bad window {name}"
        for item in win["items"]:
            for k in ["headline", "detail", "date", "league", "source_url"]:
                assert k in item, f"event item missing {k}"
            assert item["source_url"].startswith("http"), f"source_url not URL: {item['source_url']}"


def main() -> int:
    facts_path = DATA / "sports-facts.json"
    events_path = DATA / "sports-events.json"
    manifest_path = DATA / "manifest.json"
    for path in [facts_path, events_path, manifest_path]:
        assert path.exists(), f"missing {path}"
        json.loads(path.read_text())
        assert_no_obvious_secret(path)
    validate_facts(json.loads(facts_path.read_text()))
    validate_events(json.loads(events_path.read_text()))
    print("validation ok")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
