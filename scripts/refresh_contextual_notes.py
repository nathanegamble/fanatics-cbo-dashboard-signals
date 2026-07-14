#!/usr/bin/env python3
"""Build source-backed Contextual Note candidates for Claude Cowork.

This is an assistive layer, not final executive copy. It turns the structured
facts/events feeds into short, auditable note candidates with dashboard-slot
hints and citations. Cowork should adapt, verify tone, and decide placement.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

SLOT_BY_RELEVANCE = {
    "seasonality": ["today_read", "league_momentum"],
    "historical_context": ["bigger_picture", "what_moving"],
    "culture": ["bigger_picture", "creative_programs"],
    "roster_market": ["what_moving", "league_momentum"],
    "merch_demand": ["what_moving", "creative_programs"],
    "competitor": ["structural_signals", "bigger_picture"],
}

NOTE_TYPE_BY_RELEVANCE = {
    "seasonality": "seasonality",
    "historical_context": "historical_context",
    "culture": "cultural_context",
    "roster_market": "roster_market_context",
    "merch_demand": "demand_signal",
    "competitor": "competitor_watch",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:80] or "note"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text())


def phase_note(league: dict[str, Any], as_of: str) -> dict[str, Any] | None:
    confidence = league.get("phase_confidence", "low")
    phase = str(league.get("season_phase") or "unknown")
    detail = league.get("phase_detail")
    name = league.get("league", "")
    basis = league.get("phase_basis", "")
    if phase == "unknown":
        return None
    if confidence == "low" and not league.get("warnings"):
        return None
    summary = f"{name} is currently marked {phase} ({detail})."
    why = "Use this to keep dashboard language seasonally accurate; avoid saying a league is starting, peaking, or finished unless the phase supports it."
    if confidence == "low":
        why = "Use cautiously: this is useful for avoiding obvious seasonality errors, but Cowork should phrase softly or verify before making a strong claim."
    return {
        "id": f"{as_of}-{slugify(name)}-season-phase",
        "generated_from": "sports-facts.json",
        "topic": name,
        "league": name,
        "note_type": "seasonality",
        "dashboard_slots": ["today_read", "league_momentum", "bigger_picture"],
        "summary": summary,
        "why_it_matters": why,
        "supporting_facts": [basis],
        "suggested_copy": f"Seasonality check: {name} is {phase.replace('-', ' ')} as of {as_of}; {basis[:180]}",
        "confidence": confidence,
        "sources": [
            {
                "name": league.get("source_detail", {}).get("provider", "api-sports.io"),
                "url": "https://www.api-sports.io/",
                "type": "data_provider",
            }
        ],
        "warnings": league.get("warnings", []),
    }


def event_note(item: dict[str, Any], window: str, window_start: str, window_end: str) -> dict[str, Any] | None:
    relevance = item.get("relevance") or ["culture"]
    headline = item.get("headline", "")
    detail = item.get("detail") or ""
    combined_low = f"{headline} {detail}".lower()
    # Avoid pushing crime/legal tragedy into executive Contextual Note candidates
    # unless a human explicitly asks for reputation-risk monitoring.
    if any(term in combined_low for term in ["attempted murder", "charged with", "arrested", "domestic violence", "lawsuit", "death", "died"]):
        return None
    slots: list[str] = []
    for tag in relevance:
        for slot in SLOT_BY_RELEVANCE.get(tag, ["bigger_picture"]):
            if slot not in slots:
                slots.append(slot)
    note_type = NOTE_TYPE_BY_RELEVANCE.get(relevance[0], "cultural_context")
    league = item.get("league", "multi")
    headline = item.get("headline", "")
    detail = item.get("detail") or ""
    topic = f"{league}: {headline}"
    why = "Potential context note because it is a recent, sourced signal in a league/category Fanatics sells."
    if "merch_demand" in relevance:
        why = "Potential demand signal for licensed merchandise, player/team interest, or creative programming."
    elif "historical_context" in relevance:
        why = "Potential historical/cultural framing for an executive note, especially if linked to records, playoffs, titles, or milestones."
    elif "seasonality" in relevance:
        why = "Potential timing cue for keeping commentary aligned to what is happening now or soon."
    return {
        "id": f"{item.get('date', window_start)}-{slugify(headline)}",
        "generated_from": "sports-events.json",
        "topic": topic,
        "league": league,
        "note_type": note_type,
        "dashboard_slots": slots[:3],
        "window": window,
        "window_start": window_start,
        "window_end": window_end,
        "summary": headline,
        "why_it_matters": why,
        "supporting_facts": [detail] if detail else [],
        "suggested_copy": f"{headline} — {detail[:220]}" if detail else headline,
        "confidence": item.get("confidence", "medium"),
        "relevance": relevance,
        "sources": [
            {
                "name": item.get("source_name", "source"),
                "url": item.get("source_url", ""),
                "type": "article",
                "published_at": item.get("published_at"),
            }
        ],
        "warnings": [],
    }


def refresh() -> dict[str, Any]:
    facts = load_json("sports-facts.json")
    events = load_json("sports-events.json")
    as_of = facts.get("as_of") or events.get("as_of") or datetime.now(timezone.utc).date().isoformat()
    notes: list[dict[str, Any]] = []

    # Seasonality notes are compact and always useful to Cowork.
    for league in facts.get("leagues", []):
        note = phase_note(league, as_of)
        if note:
            notes.append(note)

    # Event notes: take top current/recent items, preserving source URLs.
    for window_name, window in events.get("windows", {}).items():
        items = window.get("items", [])
        for item in items[:8]:
            if item.get("source_url"):
                note = event_note(item, window_name, window.get("window_start", as_of), window.get("window_end", as_of))
                if note:
                    notes.append(note)

    # Dedupe by source URL/headline, cap for a concise daily feed.
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for note in notes:
        first_source = note.get("sources", [{}])[0]
        key = note["id"] if first_source.get("type") == "data_provider" else (first_source.get("url") or note["id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(note)

    status = "ok" if deduped else "error"
    return {
        "generated_at": utc_now(),
        "as_of": as_of,
        "source": "Derived from sports-facts.json and sports-events.json",
        "version": "0.1",
        "status": status,
        "warnings": [
            "These are candidate notes for Cowork to adapt, not final executive-dashboard prose.",
            "Cowork should verify tone, suppress low-confidence items where appropriate, and cite source URLs in final notes.",
            "Crime/legal tragedy items are filtered out of candidates by default; add a separate reputation-risk feed if needed.",
        ],
        "intended_use": "Candidate Contextual Notes for the Fanatics CBO dashboard executive-intelligence layer.",
        "candidate_count": len(deduped[:60]),
        "candidates": deduped[:60],
    }


def main() -> int:
    out = refresh()
    (DATA / "contextual-notes-candidates.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"wrote": "data/contextual-notes-candidates.json", "status": out["status"], "candidate_count": out["candidate_count"]}, indent=2))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
