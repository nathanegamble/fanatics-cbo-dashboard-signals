#!/usr/bin/env python3
"""Refresh data/sports-events.json from public, sourced sports news feeds.

POC note: Cowork requested Yahoo Scout/browser scrape as Path B. This automated
script uses public RSS/news endpoints with source URLs so the daily job is stable.
Manual Yahoo Scout/browser validation can be layered in without changing the
published schema.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

FEEDS = [
    {"name": "ESPN Top Headlines", "url": "https://www.espn.com/espn/rss/news", "default_league": "multi"},
    {"name": "ESPN NFL", "url": "https://www.espn.com/espn/rss/nfl/news", "default_league": "NFL"},
    {"name": "ESPN MLB", "url": "https://www.espn.com/espn/rss/mlb/news", "default_league": "MLB"},
    {"name": "ESPN NBA", "url": "https://www.espn.com/espn/rss/nba/news", "default_league": "NBA"},
    {"name": "ESPN NHL", "url": "https://www.espn.com/espn/rss/nhl/news", "default_league": "NHL"},
    {"name": "ESPN Soccer", "url": "https://www.espn.com/espn/rss/soccer/news", "default_league": "Soccer"},
    {"name": "ESPN College Football", "url": "https://www.espn.com/espn/rss/ncf/news", "default_league": "NCAA Football"},
    {"name": "ESPN College Basketball", "url": "https://www.espn.com/espn/rss/ncb/news", "default_league": "NCAA Basketball"},
    {"name": "ESPN WNBA", "url": "https://www.espn.com/espn/rss/wnba/news", "default_league": "WNBA"},
]

LEAGUE_KEYWORDS = [
    ("NFL", ["nfl", "super bowl", "quarterback", "draft"]),
    ("MLB", ["mlb", "baseball", "world series", "all-star", "yankees", "dodgers"]),
    ("NBA", ["nba", "basketball", "finals", "lakers", "celtics"]),
    ("WNBA", ["wnba", "liberty", "aces", "fever", "sky", "lynx"]),
    ("NHL", ["nhl", "hockey", "stanley cup"]),
    ("NCAA Football", ["college football", "ncaa football", "cfb"]),
    ("NCAA Basketball", ["college basketball", "ncaa basketball", "march madness", "ncaam", "ncaaw"]),
    ("Soccer", ["soccer", "world cup", "mls", "fifa", "premier league", "champions league", "club world cup"]),
    ("UFC", ["ufc", "mma"]),
    ("NASCAR", ["nascar"]),
    ("F1", ["formula 1", "f1", "grand prix"]),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def fetch_feed(feed: dict[str, str]) -> tuple[list[dict[str, Any]], str | None]:
    req = urllib.request.Request(feed["url"], headers={"User-Agent": "fanatics-cbo-dashboard-signals/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
    except Exception as exc:
        return [], f"{feed['name']} fetch failed: {type(exc).__name__}: {str(exc)[:160]}"
    try:
        root = ET.fromstring(body)
    except Exception as exc:
        return [], f"{feed['name']} parse failed: {type(exc).__name__}: {str(exc)[:160]}"
    items = []
    for item in root.findall(".//item")[:20]:
        title = clean(item.findtext("title", ""))
        desc = clean(item.findtext("description", ""))
        link = clean(item.findtext("link", ""))
        pub = parse_dt(item.findtext("pubDate", "") or item.findtext("published", ""))
        if not title or not link:
            continue
        items.append({
            "headline": title,
            "detail": desc[:350],
            "date": str((pub or utc_now()).date()),
            "published_at": (pub or utc_now()).isoformat(),
            "league": infer_league(title + " " + desc, feed.get("default_league", "multi")),
            "source_name": feed["name"],
            "source_url": link,
            "confidence": "medium",
            "relevance": infer_relevance(title + " " + desc),
        })
    return items, None


def infer_league(text: str, default: str) -> str:
    # Feed-specific defaults are usually more reliable than generic keywords
    # like "basketball", which can otherwise misclassify WNBA/NCAA items as NBA.
    if default and default != "multi":
        return default
    low = text.lower()
    for league, keys in LEAGUE_KEYWORDS:
        if any(k in low for k in keys):
            return league
    return default


def infer_relevance(text: str) -> list[str]:
    low = text.lower()
    tags = []
    if any(k in low for k in ["jersey", "merch", "collectible", "memorabilia", "fanatics"]):
        tags.append("merch_demand")
    if any(k in low for k in ["injury", "trade", "sign", "draft", "contract", "free agent"]):
        tags.append("roster_market")
    if any(k in low for k in ["record", "historic", "first", "milestone", "championship", "final", "playoff"]):
        tags.append("historical_context")
    if any(k in low for k in ["world cup", "all-star", "opening", "final", "schedule", "season"]):
        tags.append("seasonality")
    if any(k in low for k in ["nike", "adidas", "new era", "dick's", "lids", "retailer"]):
        tags.append("competitor")
    if not tags:
        tags.append("culture")
    return tags


def build_windows(items: list[dict[str, Any]], today: date) -> dict[str, Any]:
    windows = {
        "yesterday": {"window_start": str(today - timedelta(days=1)), "window_end": str(today - timedelta(days=1)), "items": []},
        "today": {"window_start": str(today), "window_end": str(today), "items": []},
        "this_week": {"window_start": str(today), "window_end": str(today + timedelta(days=7)), "items": []},
        "this_month": {"window_start": str(today), "window_end": str(today + timedelta(days=30)), "items": []},
        "next_month": {"window_start": str(today + timedelta(days=31)), "window_end": str(today + timedelta(days=60)), "items": []},
    }
    seen = set()
    for item in sorted(items, key=lambda x: x.get("published_at", ""), reverse=True):
        key = item["source_url"]
        if key in seen:
            continue
        seen.add(key)
        item_date = date.fromisoformat(item["date"])
        # RSS is retrospective/current. Put recent stories into windows where they are useful.
        if item_date == today - timedelta(days=1):
            windows["yesterday"]["items"].append(item)
        if item_date == today:
            windows["today"]["items"].append(item)
        if today - timedelta(days=1) <= item_date <= today:
            windows["this_week"]["items"].append(item)
            windows["this_month"]["items"].append(item)
    for w in windows.values():
        w["items"] = w["items"][:12]
    return windows


def refresh() -> dict[str, Any]:
    now = utc_now()
    today = now.date()
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    for feed in FEEDS:
        got, warning = fetch_feed(feed)
        items.extend(got)
        if warning:
            warnings.append(warning)
    return {
        "generated_at": now.isoformat(),
        "as_of": str(today),
        "source": "Public ESPN RSS feeds; Yahoo Scout/browser scrape path pending validation",
        "version": "0.1",
        "status": "ok" if items and not warnings else ("partial" if items else "error"),
        "warnings": warnings + ["Automated v0.1 uses public RSS sources with URLs for reliability; Yahoo Scout browser collection remains a separately documented POC path."],
        "source_detail": {"feeds_attempted": [f["name"] for f in FEEDS], "items_collected": len(items)},
        "windows": build_windows(items, today),
    }


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = refresh()
    (DATA_DIR / "sports-events.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"wrote": "data/sports-events.json", "status": out["status"], "items_collected": out["source_detail"]["items_collected"]}, indent=2))
    return 0 if out["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
