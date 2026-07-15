# Cowork integration notes

This document explains the v0.2 public signal feed for Claude Cowork.

## Published files

- Facts: `data/sports-facts.json`
- Events: `data/sports-events.json`
- Contextual Note candidates: `data/contextual-notes-candidates.json`
- Contextual Notes playbook: `docs/contextual-notes-playbook.md`
- Status/index: `data/manifest.json`

Use raw GitHub URLs from `manifest.json` or the README.

## Enhancements vs original request

### 1. Transparent status, freshness, and report dating

Files include:

- `generated_at`
- `as_of`
- `report_date`
- `data_date`
- `status`
- `warnings`
- `version`

`report_date` is the Cowork dashboard date. `data_date` is the underlying prior-day business data represented by the component reports. For example, the 2026-07-15 dashboard report represents 2026-07-14 business data.

This lets Cowork distinguish fresh complete data from partial/fallback data and align external context to the dashboard date convention.

### 2. Derived season phase fields

Cowork requested `season_phase`. API-Sports does not provide a universal phase taxonomy across sports, so Horatio derives it and publishes the explanation.

Fields per league:

- `season_phase`: one of `off-season`, `pre-season`, `in-season`, `post-season`, `unknown`
- `phase_detail`: e.g. `regular-season`, `playoffs`, `spring-training`, `pre-season-upcoming`
- `phase_confidence`: `high`, `medium`, `low`
- `phase_basis`: explanation suitable for auditing or suppressing uncertain copy

Consumer guidance: use `season_phase` for simple language gates, and inspect `phase_confidence` before writing strong claims.

### 3. Explicit event windows and source families

The original brief represented each window as a direct array. v0.2 nests each window so date boundaries are explicit:

```json
"this_week": {
  "window_start": "YYYY-MM-DD",
  "window_end": "YYYY-MM-DD",
  "items": []
}
```

This avoids ambiguity around what "this week" or "next month" means on any given run.

Events now include `source_family`:

- `espn_rss`: precision/editorial baseline.
- `yahoo_sports_rss`: broader sports-news discovery layer.

Yahoo News sports is not included in v0.2 because validation showed weaker relevance and higher safety/noise risk for this dashboard use case. Yahoo Scout/browser scraping has been dropped for now in favor of stable public RSS endpoints.

### 4. Relevance tags for Contextual Notes

Event items include `relevance`, an array such as:

- `seasonality`
- `historical_context`
- `culture`
- `roster_market`
- `merch_demand`
- `competitor`

These are intended to help map external signals to dashboard Contextual Note slots.

### 5. Contextual Note candidates

`contextual-notes-candidates.json` is a bridge layer generated from the facts and events feeds. It gives Cowork a shortlist of source-backed note ideas with:

- `note_type`
- `dashboard_slots`
- `summary`
- `why_it_matters`
- `supporting_facts`
- `suggested_copy`
- `confidence`
- `sources`

Important: these are candidates, not final dashboard copy. Cowork should adapt wording, suppress low-confidence items, and decide whether a note belongs in the dashboard.

### 6. Contextual Notes playbook

`docs/contextual-notes-playbook.md` documents the repeatable writing/review approach for final Contextual Notes. Use it together with the candidate feed and the private dashboard report data to:

- keep commentary scoped to the reported business lines;
- avoid overclaiming beyond Fanatics.com, wholesale, and IVR/events;
- distinguish active sports moments from residual, evergreen, player-led, and product/drop demand;
- separate fast marketing levers from slower creative/campaign-dependent work;
- preserve a senior, direct voice suitable for Cameron.

### 7. Dated report snapshots

Latest files remain at `data/*.json`, but Cowork can also use durable dated snapshots:

```text
data/reports/YYYY-MM-DD/manifest.json
data/reports/YYYY-MM-DD/sports-facts.json
data/reports/YYYY-MM-DD/sports-events.json
data/reports/YYYY-MM-DD/contextual-notes-candidates.json
```

`YYYY-MM-DD` is the dashboard `report_date`. The snapshot manifest includes `data_date` for the prior-day business data represented by the component reports.

Use dated snapshots for backfills. If a snapshot has `status: partial`, inspect `warnings`; older RSS backfills may be best-effort because RSS feeds do not retain every item from the original report date.

## Known v0.2 limitations

- WNBA is not confirmed in API-Sports basketball league search; v0.2 uses a low-confidence public seasonal calendar fallback.
- API-Sports provides broad season windows for some leagues; playoff/preseason detection depends on sampled game metadata and known separate competitions.
- ESPN RSS is the precision layer; Yahoo Sports RSS is a broader discovery layer and needs dedupe/filtering before final commentary use.
- Older dated snapshots can be partial because RSS feeds may not retain all items from the original report date.
- Standings are currently left as an empty array unless/until endpoint coverage is mapped per sport within the 100-request/day limit.

## Recommended use in dashboard commentary

- If `phase_confidence` is `high` or `medium`, the generator can use season-phase language.
- If `phase_confidence` is `low`, phrase cautiously: "the available calendar suggests..." or omit phase-specific claims.
- Use `warnings` to suppress unsupported/uncertain leagues.
- For Contextual Notes, require `source_url` and prefer `relevance` tags that match the section.
- For current daily runs, use the latest top-level files after the 5:45am ET refresh.
- For backfills, use `data/reports/YYYY-MM-DD/manifest.json` where `YYYY-MM-DD` is the Cowork dashboard report date.
- Treat `source_family: yahoo_sports_rss` as breadth/discovery and verify any strong historical or rivalry claim against official/ESPN/reliable journalism before final copy.

## Future additions Horatio recommends

1. X/social trend layer for player/team/league spikes, clearly separated from factual schedule/results data.
2. Competitor and retail-watch feeds: Nike, Adidas, Lids, Dick's, league shops, collectible launches.
3. More precise standings/results once we tune API request budget per league.
4. Yahoo Scout/browser validation as a supplemental source for cultural context and richer source discovery.
