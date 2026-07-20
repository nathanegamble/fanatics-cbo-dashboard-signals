#!/usr/bin/env python3
"""Build source-backed Contextual Note candidates for Claude Cowork.

This is an assistive layer, not final executive copy. It turns the structured
facts/events feeds into short, auditable note candidates with dashboard-slot
hints and citations. Cowork should adapt, verify tone, and decide placement.
"""
from __future__ import annotations

import argparse
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


def load_json(directory: Path, name: str) -> dict[str, Any]:
    return json.loads((directory / name).read_text())


def phase_note(league: dict[str, Any], as_of: str, report_date: str | None, data_date: str | None) -> dict[str, Any] | None:
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
        "report_date": report_date,
        "data_date": data_date,
        "summary": summary,
        "why_it_matters": why,
        "supporting_facts": [basis],
        "suggested_copy": f"Seasonality check: {name} is {phase.replace('-', ' ')} as of {as_of}; {basis[:180]}",
        "confidence": confidence,
        "relevance_score": 0.25 if confidence == "low" else 0.35,
        "relevance_reason": "derived season-phase guardrail for dashboard wording; intentionally lower-ranked than sourced event candidates",
        "sources": [
            {
                "name": league.get("source_detail", {}).get("provider", "api-sports.io"),
                "url": "https://www.api-sports.io/",
                "type": "data_provider",
            }
        ],
        "warnings": league.get("warnings", []),
    }


def event_note(item: dict[str, Any], window: str, window_start: str, window_end: str, report_date: str | None, data_date: str | None) -> dict[str, Any] | None:
    relevance = item.get("relevance") or ["culture"]
    headline = item.get("headline", "")
    detail = item.get("detail") or ""
    combined_low = f"{headline} {detail}".lower()
    if any(term in combined_low for term in ["attempted murder", "charged with", "arrested", "domestic violence", "lawsuit", "death", "died", "dies", "set her on fire", "racist message"]):
        return None
    slots: list[str] = []
    for tag in relevance:
        for slot in SLOT_BY_RELEVANCE.get(tag, ["bigger_picture"]):
            if slot not in slots:
                slots.append(slot)
    note_type = NOTE_TYPE_BY_RELEVANCE.get(relevance[0], "cultural_context")
    league = item.get("league", "multi")
    topic = f"{league}: {headline}"
    why = "Potential context note because it is a recent, sourced signal in a league/category Fanatics sells."
    if "merch_demand" in relevance:
        why = "Potential demand signal for licensed merchandise, player/team interest, or creative programming."
    elif "historical_context" in relevance:
        why = "Potential historical/cultural framing for an executive note, especially if linked to verified records, playoffs, titles, or milestones."
    elif "seasonality" in relevance:
        why = "Potential timing cue for keeping commentary aligned to what is happening now or soon."
    return {
        "id": f"{item.get('date', window_start)}-{slugify(headline)}",
        "generated_from": "sports-events.json",
        "topic": topic,
        "league": league,
        "note_type": note_type,
        "dashboard_slots": slots[:3],
        "report_date": report_date,
        "data_date": data_date,
        "window": window,
        "window_start": window_start,
        "window_end": window_end,
        "summary": headline,
        "why_it_matters": why,
        "supporting_facts": [detail] if detail else [],
        "suggested_copy": f"{headline} — {detail[:220]}" if detail else headline,
        "confidence": item.get("confidence", "medium"),
        "relevance": relevance,
        "relevance_score": item.get("relevance_score"),
        "relevance_reason": item.get("relevance_reason"),
        "source_family": item.get("source_family"),
        "sources": [
            {
                "name": item.get("source_name", "source"),
                "url": item.get("source_url", ""),
                "type": "article",
                "source_family": item.get("source_family"),
                "source_rank": item.get("source_rank"),
                "feed": item.get("feed") or item.get("feed_url"),
                "feed_url": item.get("feed_url"),
                "published": item.get("published") or item.get("published_at"),
                "published_at": item.get("published_at"),
            }
        ],
        "warnings": [],
    }


def refresh(input_dir: Path) -> dict[str, Any]:
    facts = load_json(input_dir, "sports-facts.json")
    events = load_json(input_dir, "sports-events.json")
    report_date = events.get("report_date") or facts.get("report_date") or events.get("as_of") or facts.get("as_of")
    data_date = events.get("data_date") or facts.get("data_date")
    as_of = report_date or facts.get("as_of") or datetime.now(timezone.utc).date().isoformat()
    notes: list[dict[str, Any]] = []

    for league in facts.get("leagues", []):
        note = phase_note(league, as_of, report_date, data_date)
        if note:
            notes.append(note)

    for window_name, window in events.get("windows", {}).items():
        # Skip aliases to avoid duplicating the same data_date/report_date items.
        if window_name in {"yesterday", "today"}:
            continue
        items = sorted(window.get("items", []), key=lambda x: (int(x.get("source_rank", 0)), x.get("relevance_score") or 0, x.get("published_at", "")), reverse=True)
        for item in items[:10]:
            if item.get("source_url"):
                note = event_note(item, window_name, window.get("window_start", as_of), window.get("window_end", as_of), report_date, data_date)
                if note:
                    notes.append(note)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for note in sorted(notes, key=lambda n: (n.get("relevance_score") or 0, n.get("confidence") == "high"), reverse=True):
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
        "report_date": report_date,
        "data_date": data_date,
        "report_date_basis": "Cowork dashboard report date follows receipt/publication date; underlying business data represents the prior day.",
        "source": "Derived from sports-facts.json and sports-events.json",
        "version": "0.2",
        "status": status,
        "warnings": [
            "These are candidate notes for Cowork to adapt, not final executive-dashboard prose.",
            "Cowork should verify tone, suppress low-confidence items where appropriate, and cite source URLs in final notes.",
            "Crime/legal tragedy items are filtered out of candidates by default; add a separate reputation-risk feed if needed.",
            "Yahoo Sports RSS is a breadth/discovery layer; use official/ESPN sources for stronger factual sports-history claims when possible.",
        ],
        "intended_use": "Candidate Contextual Notes for the Fanatics CBO dashboard executive-intelligence layer.",
        "candidate_count": len(deduped[:80]),
        "candidates": deduped[:80],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(DATA))
    parser.add_argument("--output-dir", default=str(DATA))
    parser.add_argument("--report-date")  # accepted for orchestration compatibility; source JSON carries truth
    parser.add_argument("--data-date")
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = refresh(input_dir)
    if args.report_date:
        out["report_date"] = args.report_date
        out["as_of"] = args.report_date
    if args.data_date:
        out["data_date"] = args.data_date
    (output_dir / "contextual-notes-candidates.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"wrote": str(output_dir / "contextual-notes-candidates.json"), "status": out["status"], "candidate_count": out["candidate_count"], "report_date": out.get("report_date"), "data_date": out.get("data_date")}, indent=2))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
