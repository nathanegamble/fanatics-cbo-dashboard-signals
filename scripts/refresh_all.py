#!/usr/bin/env python3
"""Run all refreshers, validate JSON, update manifest, and write dated snapshots."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=240)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def parse_date(value: str | None, fallback: date) -> date:
    return date.fromisoformat(value) if value else fallback


def add_report_metadata(obj: dict, report_date: date, data_date: date) -> dict:
    obj = dict(obj)
    obj["report_date"] = str(report_date)
    obj["data_date"] = str(data_date)
    obj.setdefault("as_of", str(report_date))
    obj["report_date_basis"] = "Cowork dashboard report date follows receipt/publication date; underlying business data represents the prior day."
    return obj


def build_manifest(report_date: date, data_date: date, facts: dict, events: dict, notes: dict, results: dict, snapshot_rel: str | None = None) -> dict:
    raw_base = "https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data"
    ok_statuses = {"ok", "partial"}
    path_prefix = f"{snapshot_rel}/" if snapshot_rel else ""
    raw_prefix = f"{raw_base}/{snapshot_rel}" if snapshot_rel else raw_base
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if facts.get("status") in ok_statuses and events.get("status") in ok_statuses and notes.get("status") in ok_statuses else "error",
        "version": "0.2",
        "report_date": str(report_date),
        "data_date": str(data_date),
        "report_date_basis": "Cowork dashboard report date follows receipt/publication date; underlying business data represents the prior day.",
        "source_families": events.get("source_detail", {}).get("source_families", []),
        "files": {
            "sports_facts": {"path": f"data/{path_prefix}sports-facts.json", "raw_url": f"{raw_prefix}/sports-facts.json", "status": facts.get("status"), "as_of": facts.get("as_of"), "report_date": str(report_date), "data_date": str(data_date)},
            "sports_events": {"path": f"data/{path_prefix}sports-events.json", "raw_url": f"{raw_prefix}/sports-events.json", "status": events.get("status"), "as_of": events.get("as_of"), "report_date": str(report_date), "data_date": str(data_date)},
            "contextual_notes_candidates": {"path": f"data/{path_prefix}contextual-notes-candidates.json", "raw_url": f"{raw_prefix}/contextual-notes-candidates.json", "status": notes.get("status"), "as_of": notes.get("as_of"), "report_date": str(report_date), "data_date": str(data_date), "candidate_count": notes.get("candidate_count")},
        },
        "run_results": results,
        "consumer_notes": [
            "sports-facts.json includes derived season_phase plus phase_detail, phase_basis, and phase_confidence.",
            "sports-events.json uses ESPN RSS as a precision layer and Yahoo Sports RSS as a breadth/discovery layer.",
            "sports-events.json keeps Cowork's window concept and adds report_date/data_date for the dashboard date convention.",
            "contextual-notes-candidates.json provides source-backed candidate notes and dashboard-slot hints for Cowork to adapt, not final prose.",
            "All committed outputs are public sports facts/news references; no API keys or credentials are written.",
        ],
    }


def write_snapshot(report_date: date, data_date: date, facts: dict, events: dict, notes: dict, results: dict) -> dict:
    snapshot_rel = f"reports/{report_date}"
    snapshot_dir = DATA / snapshot_rel
    facts_s = add_report_metadata(facts, report_date, data_date)
    events_s = add_report_metadata(events, report_date, data_date)
    notes_s = add_report_metadata(notes, report_date, data_date)
    write_json(snapshot_dir / "sports-facts.json", facts_s)
    write_json(snapshot_dir / "sports-events.json", events_s)
    write_json(snapshot_dir / "contextual-notes-candidates.json", notes_s)
    manifest = build_manifest(report_date, data_date, facts_s, events_s, notes_s, results, snapshot_rel=snapshot_rel)
    write_json(snapshot_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-date")
    parser.add_argument("--data-date")
    parser.add_argument("--backfill-mode", default="latest", choices=["latest", "best_effort_from_current_rss"])
    parser.add_argument("--snapshot-only", action="store_true", help="Do not overwrite latest top-level JSON; write only data/reports/YYYY-MM-DD snapshot")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).date()
    report_date = parse_date(args.report_date, today)
    data_date = parse_date(args.data_date, report_date - timedelta(days=1))
    out_dir = DATA if not args.snapshot_only else DATA / "_tmp" / str(report_date)
    if out_dir.exists() and args.snapshot_only:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    exit_code = 0

    # API-Sports facts remain latest/public sports metadata. We annotate report_date/data_date after generation.
    if args.snapshot_only:
        # Reuse latest facts for backfill to preserve API quota and avoid pretending API state is historical.
        src_facts = DATA / "sports-facts.json"
        if not src_facts.exists():
            code, output = run([sys.executable, str(ROOT / "scripts" / "refresh_api_sports.py")])
            results["refresh_api_sports.py"] = {"exit_code": code, "output": output[-2000:]}
            if code != 0:
                exit_code = code
        else:
            shutil.copy2(src_facts, out_dir / "sports-facts.json")
            results["refresh_api_sports.py"] = {"exit_code": 0, "output": "reused latest sports-facts.json for dated snapshot"}
    else:
        code, output = run([sys.executable, str(ROOT / "scripts" / "refresh_api_sports.py")])
        results["refresh_api_sports.py"] = {"exit_code": code, "output": output[-2000:]}
        if code != 0:
            exit_code = code

    event_args = [sys.executable, str(ROOT / "scripts" / "refresh_events.py"), "--report-date", str(report_date), "--data-date", str(data_date), "--output-dir", str(out_dir), "--backfill-mode", args.backfill_mode]
    code, output = run(event_args)
    results["refresh_events.py"] = {"exit_code": code, "output": output[-2000:]}
    if code != 0:
        exit_code = code

    code, output = run([sys.executable, str(ROOT / "scripts" / "refresh_contextual_notes.py"), "--input-dir", str(out_dir), "--output-dir", str(out_dir), "--report-date", str(report_date), "--data-date", str(data_date)])
    results["refresh_contextual_notes.py"] = {"exit_code": code, "output": output[-2000:]}
    if code != 0:
        exit_code = code

    facts = add_report_metadata(load(out_dir / "sports-facts.json"), report_date, data_date)
    events = add_report_metadata(load(out_dir / "sports-events.json"), report_date, data_date)
    notes = add_report_metadata(load(out_dir / "contextual-notes-candidates.json"), report_date, data_date)

    if not args.snapshot_only:
        write_json(DATA / "sports-facts.json", facts)
        write_json(DATA / "sports-events.json", events)
        write_json(DATA / "contextual-notes-candidates.json", notes)

    snapshot_manifest = write_snapshot(report_date, data_date, facts, events, notes, results)

    # Latest manifest indexes all available dated snapshots.
    available = []
    for p in sorted((DATA / "reports").glob("*/manifest.json")):
        try:
            m = load(p)
            available.append({
                "report_date": m.get("report_date"),
                "data_date": m.get("data_date"),
                "status": m.get("status"),
                "path": f"data/reports/{p.parent.name}/manifest.json",
                "raw_url": f"https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data/reports/{p.parent.name}/manifest.json",
            })
        except Exception:
            continue
    available = sorted(available, key=lambda x: x.get("report_date") or "")

    manifest = build_manifest(report_date, data_date, facts, events, notes, results)
    manifest["latest_report_date"] = str(report_date)
    manifest["latest_data_date"] = str(data_date)
    manifest["available_reports"] = available
    manifest["dated_snapshot"] = {
        "path": f"data/reports/{report_date}/manifest.json",
        "raw_url": f"https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data/reports/{report_date}/manifest.json",
        "status": snapshot_manifest.get("status"),
    }
    if not args.snapshot_only:
        write_json(DATA / "manifest.json", manifest)
    elif not (DATA / "manifest.json").exists():
        write_json(DATA / "manifest.json", manifest)
    else:
        # Preserve latest top-level files but refresh available_reports index.
        latest = load(DATA / "manifest.json")
        latest["available_reports"] = available
        write_json(DATA / "manifest.json", latest)

    print(json.dumps({"status": manifest["status"], "report_date": str(report_date), "data_date": str(data_date), "snapshot": f"data/reports/{report_date}/", "available_reports": len(available)}, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
