#!/usr/bin/env python3
"""Validation for public JSON outputs and dated report snapshots."""
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
DISALLOWED_CANDIDATE_TERMS = ["attempted murder", "charged with", "arrested", "domestic violence", "set her on fire", "racist message"]


def load(path: Path) -> dict:
    return json.loads(path.read_text())


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
    if obj.get("version") == "0.2":
        for key in ["report_date", "data_date", "report_date_basis"]:
            assert key in obj, f"sports-events missing {key}"
    for name in ["yesterday", "today", "this_week", "this_month", "next_month"]:
        assert name in obj["windows"], f"missing window {name}"
        win = obj["windows"][name]
        assert "window_start" in win and "window_end" in win and "items" in win, f"bad window {name}"
        for item in win["items"]:
            for k in ["headline", "detail", "date", "league", "source_url"]:
                assert k in item, f"event item missing {k}"
            assert item["source_url"].startswith("http"), f"source_url not URL: {item['source_url']}"
            if obj.get("version") == "0.2":
                assert item.get("source_family") in {"espn_rss", "yahoo_sports_rss"}, f"bad/missing source_family: {item.get('source_family')}"
                assert str(item.get("feed_url", "")).startswith("http"), f"missing feed_url: {item.get('headline')}"
                assert isinstance(item.get("relevance_score"), (int, float)), f"missing relevance_score: {item.get('headline')}"


def validate_notes(obj: dict) -> None:
    for key in ["generated_at", "as_of", "status", "warnings", "candidates"]:
        assert key in obj, f"contextual-notes-candidates missing {key}"
    assert isinstance(obj["candidates"], list) and obj["candidates"], "contextual note candidates empty"
    for note in obj["candidates"]:
        for k in ["id", "topic", "note_type", "dashboard_slots", "summary", "why_it_matters", "confidence", "sources"]:
            assert k in note, f"candidate missing {k}"
        text = json.dumps(note).lower()
        for term in DISALLOWED_CANDIDATE_TERMS:
            assert term not in text, f"disallowed safety term in candidate {note.get('id')}: {term}"
        assert isinstance(note["dashboard_slots"], list), f"dashboard_slots not list: {note.get('id')}"
        assert isinstance(note["sources"], list) and note["sources"], f"candidate missing sources: {note.get('id')}"
        for source in note["sources"]:
            assert source.get("url", "").startswith("http"), f"candidate source_url not URL: {note.get('id')}"


def validate_manifest(obj: dict, base: Path) -> None:
    assert obj.get("status") in {"ok", "partial", "error"}, "manifest missing/bad status"
    if obj.get("version") == "0.2":
        for key in ["report_date", "data_date", "files"]:
            assert key in obj, f"manifest missing {key}"
    for file_info in obj.get("files", {}).values():
        p = ROOT / file_info.get("path", "")
        assert p.exists(), f"manifest points to missing file: {p}"
        assert str(file_info.get("raw_url", "")).startswith("https://raw.githubusercontent.com/"), "manifest raw_url invalid"


def validate_bundle(directory: Path) -> None:
    facts_path = directory / "sports-facts.json"
    events_path = directory / "sports-events.json"
    notes_path = directory / "contextual-notes-candidates.json"
    manifest_path = directory / "manifest.json"
    for path in [facts_path, events_path, notes_path, manifest_path]:
        assert path.exists(), f"missing {path}"
        load(path)
        assert_no_obvious_secret(path)
    validate_facts(load(facts_path))
    validate_events(load(events_path))
    validate_notes(load(notes_path))
    validate_manifest(load(manifest_path), directory)


def main() -> int:
    validate_bundle(DATA)
    reports = sorted((DATA / "reports").glob("*/manifest.json"))
    for manifest in reports:
        validate_bundle(manifest.parent)
    print(f"validation ok ({1 + len(reports)} bundles)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
