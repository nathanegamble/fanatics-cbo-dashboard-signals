#!/usr/bin/env python3
"""Refresh data/sports-facts.json from API-Sports plus documented fallbacks.

Secrets: reads API_SPORTS_KEY from environment or ~/.hermes/.env. The key is never
written to output. Output is public, non-sensitive sports metadata.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
API_KEY_RE = re.compile(r"^API_SPORTS_KEY=(.+)$", re.M)


@dataclass
class ApiLeague:
    display: str
    sport: str
    api_base: str | None
    api_kind: str | None
    league_id: int | None
    season_field: str
    aliases: list[str]
    preseason_competitions: list[tuple[str, str, int]]
    fallback_calendar: dict[str, Any] | None = None


LEAGUES: list[ApiLeague] = [
    ApiLeague("NFL", "american-football", "https://v1.american-football.api-sports.io", "american-football", 1, "year", [], []),
    ApiLeague("NCAA Football", "american-football", "https://v1.american-football.api-sports.io", "american-football", 2, "year", ["CFB"], []),
    ApiLeague("MLB", "baseball", "https://v1.baseball.api-sports.io", "baseball", 1, "season", [], [("MLB Spring Training", "https://v1.baseball.api-sports.io", 71)]),
    ApiLeague("NBA", "basketball", "https://v1.basketball.api-sports.io", "basketball", 12, "season", [], []),
    ApiLeague("WNBA", "basketball", None, None, None, "season", [], [], {
        "source": "manual-public-calendar-seed",
        "note": "API-Sports basketball search did not expose WNBA in POC checks; derive from public WNBA seasonal norms until a licensed endpoint is added.",
        "typical_start_month_day": "05-01",
        "typical_regular_end_month_day": "09-15",
        "typical_postseason_end_month_day": "10-20",
    }),
    ApiLeague("NCAA Basketball", "basketball", "https://v1.basketball.api-sports.io", "basketball", 116, "season", ["NCAAM"], []),
    ApiLeague("NCAA Women's Basketball", "basketball", "https://v1.basketball.api-sports.io", "basketball", 423, "season", ["NCAAW"], []),
    ApiLeague("NHL", "hockey", "https://v1.hockey.api-sports.io", "hockey", 57, "season", [], []),
    ApiLeague("MLS", "soccer", "https://v3.football.api-sports.io", "football", 253, "year", [], []),
    ApiLeague("FIFA World Cup", "soccer", "https://v3.football.api-sports.io", "football", 1, "year", ["World Cup"], []),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_key() -> str:
    if os.getenv("API_SPORTS_KEY"):
        return os.environ["API_SPORTS_KEY"].strip()
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        m = API_KEY_RE.search(env_path.read_text(errors="ignore"))
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


class ApiSportsClient:
    def __init__(self, key: str):
        self.key = key
        self.requests = 0
        self.errors: list[str] = []

    def get(self, base: str, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        url = base + endpoint
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"x-apisports-key": self.key})
        self.requests += 1
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # fail loud into JSON, not silently
            msg = f"{endpoint} failed: {type(exc).__name__}: {str(exc)[:180]}"
            self.errors.append(msg)
            return {"errors": {"client": msg}, "response": []}


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    s = str(value)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def season_label(season: dict[str, Any], field: str) -> str:
    return str(season.get(field) or season.get("year") or season.get("season") or "")


def pick_relevant_season(seasons: list[dict[str, Any]], today: date, field: str) -> dict[str, Any] | None:
    if not seasons:
        return None
    def key(s: dict[str, Any]) -> tuple[int, str]:
        start, end = parse_date(s.get("start")), parse_date(s.get("end"))
        active = int(bool(start and end and start <= today <= end) or bool(s.get("current")))
        return (active, season_label(s, field))
    return sorted(seasons, key=key, reverse=True)[0]


def get_league_metadata(client: ApiSportsClient, league: ApiLeague) -> tuple[dict[str, Any] | None, list[str]]:
    if not league.api_base or league.league_id is None:
        return None, []
    endpoint = "/leagues"
    data = client.get(league.api_base, endpoint, {"id": league.league_id})
    warnings: list[str] = []
    if data.get("errors"):
        warnings.append(f"API errors from {league.display} league lookup: {data.get('errors')}")
    resp = data.get("response") or []
    return (resp[0] if resp else None), warnings


def get_games(client: ApiSportsClient, league: ApiLeague, season_id: str, today: date, window_days: int = 7) -> list[dict[str, Any]]:
    if not league.api_base or league.league_id is None or not season_id:
        return []
    if league.api_kind == "football":
        endpoint = "/fixtures"
        params = {"league": league.league_id, "season": season_id, "from": str(today - timedelta(days=window_days)), "to": str(today + timedelta(days=window_days))}
    else:
        endpoint = "/games"
        params = {"league": league.league_id, "season": season_id}
    data = client.get(league.api_base, endpoint, params)
    return data.get("response") or []


def compact_game(g: dict[str, Any], api_kind: str | None) -> dict[str, Any] | None:
    try:
        if api_kind == "football":
            dt = (g.get("fixture") or {}).get("date", "")[:10]
            home = ((g.get("teams") or {}).get("home") or {}).get("name", "")
            away = ((g.get("teams") or {}).get("away") or {}).get("name", "")
            goals = g.get("goals") or {}
            score = "" if goals.get("home") is None else f"{goals.get('home')}-{goals.get('away')}"
            status = ((g.get("fixture") or {}).get("status") or {}).get("short", "")
            note = ((g.get("league") or {}).get("round") or status or "")
        else:
            dt = str(g.get("date") or g.get("time") or "")[:10]
            teams = g.get("teams") or {}
            home = ((teams.get("home") or {}).get("name") or "")
            away = ((teams.get("away") or {}).get("name") or "")
            scores = g.get("scores") or {}
            hs = (scores.get("home") or {}).get("total")
            aw = (scores.get("away") or {}).get("total")
            score = "" if hs is None else f"{hs}-{aw}"
            note = str(g.get("stage") or g.get("status", {}).get("long") or g.get("status", {}).get("short") or "")
        if not (dt and home and away):
            return None
        return {"date": dt, "home": home, "away": away, "score": score, "note": note}
    except Exception:
        return None


def derive_phase(league: ApiLeague, season: dict[str, Any] | None, games: list[dict[str, Any]], today: date, preseason_active: bool) -> dict[str, str]:
    if league.fallback_calendar:
        # WNBA fallback: coarse public seasonal norms, explicit low confidence.
        year = today.year
        start = date.fromisoformat(f"{year}-{league.fallback_calendar['typical_start_month_day']}")
        reg_end = date.fromisoformat(f"{year}-{league.fallback_calendar['typical_regular_end_month_day']}")
        post_end = date.fromisoformat(f"{year}-{league.fallback_calendar['typical_postseason_end_month_day']}")
        if today < start:
            phase, detail = "off-season", "off-season"
        elif start <= today <= reg_end:
            phase, detail = "in-season", "regular-season"
        elif today <= post_end:
            phase, detail = "post-season", "playoffs"
        else:
            phase, detail = "off-season", "off-season"
        return {"season_phase": phase, "phase_detail": detail, "phase_confidence": "low", "phase_basis": league.fallback_calendar["note"]}

    if preseason_active:
        return {"season_phase": "pre-season", "phase_detail": "spring-training", "phase_confidence": "high", "phase_basis": "Separate API-Sports preseason/training competition is active."}

    start = parse_date((season or {}).get("start"))
    end = parse_date((season or {}).get("end"))
    game_text = " ".join(json.dumps(g).lower() for g in games[:25])
    if any(token in game_text for token in ["playoff", "postseason", "post-season", "final", "world series", "stanley cup", "super bowl", "conference championship", "wild card", "knockout"]):
        return {"season_phase": "post-season", "phase_detail": "playoffs", "phase_confidence": "medium", "phase_basis": "Recent/scheduled API game metadata contains playoff/final markers."}
    if any(token in game_text for token in ["preseason", "pre-season", "spring training", "training"]):
        return {"season_phase": "pre-season", "phase_detail": "preseason", "phase_confidence": "medium", "phase_basis": "Recent/scheduled API game metadata contains preseason/training markers."}
    if start and end and start <= today <= end:
        return {"season_phase": "in-season", "phase_detail": "regular-season", "phase_confidence": "medium", "phase_basis": "Current date falls inside API-Sports league season window; no playoff/preseason markers detected in sampled game metadata."}
    if start and today < start:
        days = (start - today).days
        return {"season_phase": "off-season", "phase_detail": "pre-season-upcoming" if days <= 45 else "off-season", "phase_confidence": "medium", "phase_basis": f"Current date is {days} days before the next API-Sports season start."}
    if end and today > end:
        return {"season_phase": "off-season", "phase_detail": "off-season", "phase_confidence": "medium", "phase_basis": "Current date is after the API-Sports season end and no active preseason competition was found."}
    return {"season_phase": "unknown", "phase_detail": "unknown", "phase_confidence": "low", "phase_basis": "Insufficient API metadata to derive season phase."}


def build_fallback_season(league: ApiLeague, today: date) -> dict[str, Any]:
    if league.display == "WNBA":
        year = today.year
        return {"season": year, "start": f"{year}-05-01", "end": f"{year}-10-20", "is_current": date(year, 5, 1) <= today <= date(year, 10, 20)}
    return {"season": "unknown", "start": None, "end": None, "is_current": False}


def refresh() -> dict[str, Any]:
    key = load_key()
    now = utc_now()
    today = now.date()
    warnings: list[str] = []
    if not key:
        return {"generated_at": now.isoformat(), "as_of": str(today), "source": "api-sports.io", "version": "0.1", "status": "error", "warnings": ["API_SPORTS_KEY missing"], "leagues": []}
    client = ApiSportsClient(key)
    leagues_out: list[dict[str, Any]] = []
    for spec in LEAGUES:
        meta, meta_warnings = get_league_metadata(client, spec)
        warnings.extend(meta_warnings)
        seasons = (meta or {}).get("seasons") or []
        season = pick_relevant_season(seasons, today, spec.season_field)
        fallback_season = build_fallback_season(spec, today)
        season_id = season_label(season or fallback_season, spec.season_field)
        games = get_games(client, spec, season_id, today) if spec.api_base else []
        compact_games = [x for x in (compact_game(g, spec.api_kind) for g in games) if x]
        compact_recent = []
        for g in compact_games:
            gd = parse_date(g["date"])
            if gd and gd <= today:
                compact_recent.append(g)
        compact_recent = compact_recent[-5:]
        preseason_active = False
        for _name, base, lid in spec.preseason_competitions:
            pre_meta, _ = get_league_metadata(client, ApiLeague(_name, spec.sport, base, spec.api_kind, lid, "season", [], []))
            pre_season = pick_relevant_season((pre_meta or {}).get("seasons") or [], today, "season")
            ps, pe = parse_date((pre_season or {}).get("start")), parse_date((pre_season or {}).get("end"))
            if ps and pe and ps <= today <= pe:
                preseason_active = True
        phase = derive_phase(spec, season, games, today, preseason_active)
        season_start = parse_date((season or {}).get("start"))
        season_end = parse_date((season or {}).get("end"))
        season_obj = {
            "label": season_id or fallback_season.get("season"),
            "start": (season or fallback_season).get("start"),
            "end": (season or fallback_season).get("end"),
            "is_current": bool((season or {}).get("current")) or bool(fallback_season.get("is_current")) or bool(season_start and season_end and season_start <= today <= season_end),
        }
        league_warnings: list[str] = []
        if spec.fallback_calendar:
            league_warnings.append(spec.fallback_calendar["note"])
        if not meta and not spec.fallback_calendar:
            league_warnings.append("No API-Sports league metadata returned.")
        provider = "api-sports.io"
        if not spec.api_base and spec.fallback_calendar:
            provider = str(spec.fallback_calendar.get("source", "documented-fallback"))
        leagues_out.append({
            "league": spec.display,
            **phase,
            "season": season_obj,
            "key_dates": [],
            "recent_results": compact_recent,
            "standings_top": [],
            "as_of": str(today),
            "source_detail": {
                "provider": provider,
                "sport_api": spec.api_kind,
                "league_id": spec.league_id,
                "aliases": spec.aliases,
            },
            "warnings": league_warnings,
        })
    warnings.extend(client.errors)
    status = "ok" if not warnings else "partial"
    return {
        "generated_at": now.isoformat(),
        "as_of": str(today),
        "source": "api-sports.io + documented fallbacks",
        "version": "0.1",
        "status": status,
        "warnings": warnings,
        "source_detail": {"provider": "api-sports.io", "request_count": client.requests, "daily_limit": 100},
        "leagues": leagues_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DATA_DIR))
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = refresh()
    output_path = output_dir / "sports-facts.json"
    output_path.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n")
    wrote = str(output_path.relative_to(ROOT)) if output_path.is_relative_to(ROOT) else str(output_path)
    print(json.dumps({"wrote": wrote, "status": out["status"], "leagues": len(out["leagues"]), "request_count": out.get("source_detail", {}).get("request_count")}, indent=2))
    return 0 if out["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
