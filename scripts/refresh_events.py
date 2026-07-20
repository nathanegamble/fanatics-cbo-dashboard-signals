#!/usr/bin/env python3
"""Refresh sports-events.json from public, sourced sports news feeds.

Uses stable RSS endpoints rather than browser scraping. ESPN is treated as the
precision editorial layer; Yahoo Sports is a broader discovery layer. Outputs
support both latest files and report-date snapshots for Cowork backfills.
"""
from __future__ import annotations

import argparse
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
    {"name": "ESPN Top Headlines", "url": "https://www.espn.com/espn/rss/news", "default_league": "multi", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN NFL", "url": "https://www.espn.com/espn/rss/nfl/news", "default_league": "NFL", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN MLB", "url": "https://www.espn.com/espn/rss/mlb/news", "default_league": "MLB", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN NBA", "url": "https://www.espn.com/espn/rss/nba/news", "default_league": "NBA", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN NHL", "url": "https://www.espn.com/espn/rss/nhl/news", "default_league": "NHL", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN Soccer", "url": "https://www.espn.com/espn/rss/soccer/news", "default_league": "Soccer", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN College Football", "url": "https://www.espn.com/espn/rss/ncf/news", "default_league": "NCAA Football", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN College Basketball", "url": "https://www.espn.com/espn/rss/ncb/news", "default_league": "NCAA Basketball", "source_family": "espn_rss", "limit": 25},
    {"name": "ESPN WNBA", "url": "https://www.espn.com/espn/rss/wnba/news", "default_league": "WNBA", "source_family": "espn_rss", "limit": 25},
    {"name": "Yahoo Sports Top", "url": "https://sports.yahoo.com/rss/", "default_league": "multi", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports NFL", "url": "https://sports.yahoo.com/nfl/rss/", "default_league": "NFL", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports MLB", "url": "https://sports.yahoo.com/mlb/rss/", "default_league": "MLB", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports NBA", "url": "https://sports.yahoo.com/nba/rss/", "default_league": "NBA", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports WNBA", "url": "https://sports.yahoo.com/wnba/rss/", "default_league": "WNBA", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports Soccer", "url": "https://sports.yahoo.com/soccer/rss/", "default_league": "Soccer", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports NHL", "url": "https://sports.yahoo.com/nhl/rss/", "default_league": "NHL", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports College Football", "url": "https://sports.yahoo.com/college-football/rss/", "default_league": "NCAA Football", "source_family": "yahoo_sports_rss", "limit": 35},
    {"name": "Yahoo Sports College Basketball", "url": "https://sports.yahoo.com/college-basketball/rss/", "default_league": "NCAA Basketball", "source_family": "yahoo_sports_rss", "limit": 35},
]

LEAGUE_KEYWORDS = [
    ("WNBA", ["wnba", "liberty", "aces", "fever", "sky", "lynx", "valkyries", "caitlin clark"]),
    ("NFL", ["nfl", "super bowl", "quarterback", "draft", "steelers", "cowboys", "bills"]),
    ("MLB", ["mlb", "baseball", "world series", "all-star", "home run derby", "yankees", "dodgers", "ohtani", "topps"]),
    ("NBA", ["nba", "basketball", "finals", "lakers", "celtics", "knicks", "summer league"]),
    ("NHL", ["nhl", "hockey", "stanley cup"]),
    ("NCAA Football", ["college football", "ncaa football", "cfb"]),
    ("NCAA Basketball", ["college basketball", "ncaa basketball", "march madness", "ncaam", "ncaaw"]),
    ("Soccer", ["soccer", "world cup", "mls", "fifa", "premier league", "champions league", "club world cup", "argentina", "england", "messi", "haaland", "kane", "bellingham"]),
    ("UFC", ["ufc", "mma"]),
    ("NASCAR", ["nascar"]),
    ("F1", ["formula 1", "f1", "grand prix"]),
]

NEGATIVE_TERMS = ["arrested", "charged", "lawsuit", "domestic violence", "murder", "death", "dies", "died", "killed", "racist message", "set her on fire"]
POSITIVE_TERMS = ["world cup", "semifinal", "semi-final", "final", "championship", "playoff", "all-star", "home run derby", "jersey", "uniform", "alternate", "merch", "collectible", "memorabilia", "topps", "card", "collaboration", "drop", "nike", "adidas", "new era", "lids", "fanatics", "messi", "haaland", "kane", "bellingham", "ohtani", "yankees", "dodgers", "knicks", "wnba", "valkyries", "argentina", "england"]
SOURCE_RANK = {"espn_rss": 2, "yahoo_sports_rss": 1, "fifa_schedule": 3}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_date_arg(value: str | None, fallback: date) -> date:
    return date.fromisoformat(value) if value else fallback


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&[#A-Za-z0-9]+;", " ", text)
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


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    qs = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith(("utm_", "guccounter"))]
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urllib.parse.urlencode(qs), ""))


def norm_title(title: str) -> str:
    title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return re.sub(r"\s+", " ", title)


def infer_league(text: str, default: str) -> str:
    if default and default != "multi":
        return default
    low = text.lower()
    for league, keys in LEAGUE_KEYWORDS:
        if any(k in low for k in keys):
            return league
    return default


def infer_relevance(text: str) -> list[str]:
    low = text.lower()
    tags: list[str] = []
    if any(k in low for k in ["jersey", "uniform", "merch", "collectible", "memorabilia", "fanatics", "topps", "card"]):
        tags.append("merch_demand")
    if any(k in low for k in ["trade", "sign", "draft", "contract", "free agent", "transfer", "lineup"]):
        tags.append("roster_market")
    if any(k in low for k in ["record", "historic", "first", "milestone", "championship", "final", "semifinal", "playoff", "world cup"]):
        tags.append("historical_context")
    if any(k in low for k in ["world cup", "all-star", "opening", "final", "semifinal", "schedule", "season", "derby", "hall of fame"]):
        tags.append("seasonality")
    if any(k in low for k in ["nike", "adidas", "new era", "dick's", "lids", "retailer", "macy", "walmart"]):
        tags.append("competitor")
    if not tags:
        tags.append("culture")
    return tags


def score_item(title: str, desc: str, source_family: str, data_date: date) -> tuple[float, str, str]:
    low = f"{title} {desc}".lower()
    score = 0.25
    reasons: list[str] = []
    if source_family == "espn_rss":
        score += 0.15; reasons.append("ESPN precision source")
    elif source_family == "yahoo_sports_rss":
        score += 0.08; reasons.append("Yahoo Sports breadth source")
    hits = [t for t in POSITIVE_TERMS if t in low]
    if hits:
        score += min(0.35, 0.06 * len(hits)); reasons.append("matches " + ", ".join(hits[:5]))
    if any(t in low for t in ["betting", "parlay", "odds"]):
        score -= 0.10; reasons.append("betting/fantasy noise risk")
    if any(t in low for t in NEGATIVE_TERMS):
        score -= 0.45; reasons.append("crime/legal/tragedy safety filter")
    confidence = "medium"
    if score >= 0.70:
        confidence = "high"
    elif score < 0.30:
        confidence = "low"
    return max(0.0, min(1.0, round(score, 2))), "; ".join(reasons) or "general sports/culture item", confidence


def fetch_feed(feed: dict[str, Any], data_date: date) -> tuple[list[dict[str, Any]], str | None]:
    req = urllib.request.Request(feed["url"], headers={"User-Agent": "fanatics-cbo-dashboard-signals/0.2"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
    except Exception as exc:
        return [], f"{feed['name']} fetch failed: {type(exc).__name__}: {str(exc)[:160]}"
    try:
        root = ET.fromstring(body)
    except Exception as exc:
        return [], f"{feed['name']} parse failed: {type(exc).__name__}: {str(exc)[:160]}"
    if root.find(".//Code") is not None and root.findtext(".//Code"):
        return [], f"{feed['name']} returned XML error: {root.findtext('.//Code')}"
    items = []
    for item in root.findall(".//item")[: int(feed.get("limit", 25))]:
        title = clean(item.findtext("title", ""))
        desc = clean(item.findtext("description", ""))
        link = clean(item.findtext("link", ""))
        pub = parse_dt(item.findtext("pubDate", "") or item.findtext("published", ""))
        if not title or not link:
            continue
        published = pub or utc_now()
        score, reason, confidence = score_item(title, desc, feed["source_family"], data_date)
        if score < 0.22:
            continue
        items.append({
            "headline": title,
            "detail": desc[:350],
            "date": str(published.date()),
            "published": published.isoformat(),
            "published_at": published.isoformat(),
            "league": infer_league(title + " " + desc, feed.get("default_league", "multi")),
            "source_name": feed["name"],
            "source_family": feed["source_family"],
            "source_rank": SOURCE_RANK.get(feed["source_family"], 0),
            "feed": feed["url"],
            "feed_url": feed["url"],
            "source_url": link,
            "canonical_url": canonical_url(link),
            "confidence": confidence,
            "relevance": infer_relevance(title + " " + desc),
            "relevance_score": score,
            "relevance_reason": reason,
        })
    return items, None


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def priority(it: dict[str, Any]) -> tuple[int, float, str]:
        source_rank = int(it.get("source_rank") or SOURCE_RANK.get(str(it.get("source_family")), 0))
        return (source_rank, float(it.get("relevance_score", 0)), it.get("published_at", ""))
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        keys = [item.get("canonical_url") or item.get("source_url"), norm_title(item.get("headline", ""))]
        keys = [k for k in keys if k]
        existing_key = next((k for k in keys if k in best), None)
        if existing_key:
            if priority(item) > priority(best[existing_key]):
                best[existing_key] = item
        else:
            best[keys[0]] = item
    return sorted(best.values(), key=lambda x: (x.get("date", ""), int(x.get("source_rank", 0)), x.get("relevance_score", 0), x.get("published_at", "")), reverse=True)


def build_windows(items: list[dict[str, Any]], report_date: date, data_date: date) -> dict[str, Any]:
    windows = {
        "data_date": {"window_start": str(data_date), "window_end": str(data_date), "items": []},
        "report_date": {"window_start": str(report_date), "window_end": str(report_date), "items": []},
        "prior_day": {"window_start": str(data_date), "window_end": str(data_date), "items": []},
        "this_week": {"window_start": str(data_date), "window_end": str(report_date + timedelta(days=7)), "items": []},
        "this_month": {"window_start": str(data_date), "window_end": str(report_date + timedelta(days=30)), "items": []},
        "next_month": {"window_start": str(report_date + timedelta(days=31)), "window_end": str(report_date + timedelta(days=60)), "items": []},
    }
    for item in items:
        item_date = date.fromisoformat(item["date"])
        if item_date == data_date:
            windows["data_date"]["items"].append(item)
            windows["prior_day"]["items"].append(item)
        if item_date == report_date:
            windows["report_date"]["items"].append(item)
        if data_date <= item_date <= report_date:
            windows["this_week"]["items"].append(item)
            windows["this_month"]["items"].append(item)
    # Backward-compatible aliases Cowork already knows.
    windows["yesterday"] = dict(windows["data_date"])
    windows["today"] = dict(windows["report_date"])
    for w in windows.values():
        w["items"] = sorted(w["items"], key=lambda x: (int(x.get("source_rank", 0)), x.get("relevance_score", 0), x.get("published_at", "")), reverse=True)[:20]
    return windows


def add_known_schedule_items(items: list[dict[str, Any]], report_date: date, data_date: date) -> list[dict[str, Any]]:
    """Add high-confidence scheduled sports moments that RSS backfills may not retain."""
    if report_date == date(2026, 7, 19) or data_date == date(2026, 7, 18):
        published = datetime.combine(data_date, datetime.min.time(), timezone.utc).replace(hour=12)
        url = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/new-york-new-jersey-stadium-host-world-cup-2026-final"
        items.append({
            "headline": "FIFA World Cup final buildup: final scheduled for July 19 at New York New Jersey Stadium",
            "detail": "FIFA confirmed New York New Jersey Stadium as host of the FIFA World Cup 2026 final on Sunday, 19 July 2026, making the tournament live through the 07-19 report window.",
            "date": str(data_date),
            "published": published.isoformat(),
            "published_at": published.isoformat(),
            "league": "Soccer",
            "source_name": "FIFA",
            "source_family": "fifa_schedule",
            "source_rank": SOURCE_RANK["fifa_schedule"],
            "feed": url,
            "feed_url": url,
            "source_url": url,
            "canonical_url": canonical_url(url),
            "confidence": "high",
            "relevance": ["seasonality", "historical_context", "merch_demand"],
            "relevance_score": 0.92,
            "relevance_reason": "official FIFA schedule confirms World Cup final timing; useful for final-week/final-day demand and executive context",
        })
    return items


def refresh(report_date: date | None = None, data_date: date | None = None, backfill_mode: str = "latest") -> dict[str, Any]:
    now = utc_now()
    report_date = report_date or now.date()
    data_date = data_date or (report_date - timedelta(days=1))
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    for feed in FEEDS:
        got, warning = fetch_feed(feed, data_date)
        items.extend(got)
        if warning:
            warnings.append(warning)
    items = dedupe_items(items)
    items = add_known_schedule_items(items, report_date, data_date)
    windows = build_windows(items, report_date, data_date)
    if backfill_mode != "latest":
        warnings.append("Backfill snapshots are best-effort from currently available RSS items; RSS feeds may not retain all items from the original report date.")
    if not windows["data_date"]["items"]:
        warnings.append(f"No RSS items retained for data_date {data_date}; use report_date/this_week items as adjacent context only.")
    status = "ok" if items and not warnings else ("partial" if items else "error")
    return {
        "generated_at": now.isoformat(),
        "as_of": str(report_date),
        "report_date": str(report_date),
        "data_date": str(data_date),
        "report_date_basis": "Cowork dashboard report date follows receipt/publication date; underlying business data represents the prior day.",
        "source": "Public ESPN RSS + Yahoo Sports RSS feeds",
        "version": "0.2",
        "status": status,
        "warnings": warnings,
        "source_detail": {
            "feeds_attempted": [f["name"] for f in FEEDS],
            "source_families": sorted({*(f["source_family"] for f in FEEDS), *(str(i.get("source_family")) for i in items if i.get("source_family"))}),
            "items_collected_after_dedupe": len(items),
            "backfill_mode": backfill_mode,
            "yahoo_news_sports": "excluded for v0.2 because quick validation showed lower relevance and higher safety/noise risk than Yahoo Sports RSS.",
        },
        "windows": windows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-date")
    parser.add_argument("--data-date")
    parser.add_argument("--output-dir", default=str(DATA_DIR))
    parser.add_argument("--backfill-mode", default="latest", choices=["latest", "best_effort_from_current_rss"])
    args = parser.parse_args()
    now_date = utc_now().date()
    report_date = parse_date_arg(args.report_date, now_date)
    data_date = parse_date_arg(args.data_date, report_date - timedelta(days=1))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = refresh(report_date, data_date, args.backfill_mode)
    (out_dir / "sports-events.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"wrote": str(out_dir / "sports-events.json"), "status": out["status"], "items_collected": out["source_detail"]["items_collected_after_dedupe"], "report_date": out["report_date"], "data_date": out["data_date"]}, indent=2))
    return 0 if out["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
