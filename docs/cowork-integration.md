# Cowork integration notes

This document explains the v0.1 enhancements beyond the original brief.

## Published files

- Facts: `data/sports-facts.json`
- Events: `data/sports-events.json`
- Status/index: `data/manifest.json`

Use raw GitHub URLs from `manifest.json` or the README.

## Enhancements vs original request

### 1. Transparent status and freshness

Both JSON files include:

- `generated_at`
- `as_of`
- `status`
- `warnings`
- `version`

This lets Cowork distinguish fresh complete data from partial/fallback data.

### 2. Derived season phase fields

Cowork requested `season_phase`. API-Sports does not provide a universal phase taxonomy across sports, so Horatio derives it and publishes the explanation.

Fields per league:

- `season_phase`: one of `off-season`, `pre-season`, `in-season`, `post-season`, `unknown`
- `phase_detail`: e.g. `regular-season`, `playoffs`, `spring-training`, `pre-season-upcoming`
- `phase_confidence`: `high`, `medium`, `low`
- `phase_basis`: explanation suitable for auditing or suppressing uncertain copy

Consumer guidance: use `season_phase` for simple language gates, and inspect `phase_confidence` before writing strong claims.

### 3. Explicit event windows

The original brief represented each window as a direct array. v0.1 nests each window so date boundaries are explicit:

```json
"this_week": {
  "window_start": "YYYY-MM-DD",
  "window_end": "YYYY-MM-DD",
  "items": []
}
```

This avoids ambiguity around what "this week" or "next month" means on any given run.

### 4. Relevance tags for Contextual Notes

Event items include `relevance`, an array such as:

- `seasonality`
- `historical_context`
- `culture`
- `roster_market`
- `merch_demand`
- `competitor`

These are intended to help map external signals to dashboard Contextual Note slots.

## Known v0.1 limitations

- WNBA is not confirmed in API-Sports basketball league search; v0.1 uses a low-confidence public seasonal calendar fallback.
- API-Sports provides broad season windows for some leagues; playoff/preseason detection depends on sampled game metadata and known separate competitions.
- `sports-events.json` v0.1 uses public ESPN RSS feeds for stable automation and source URLs. Cowork requested Yahoo Scout/browser validation; this remains the next POC layer and can publish into the same schema.
- Standings are currently left as an empty array unless/until endpoint coverage is mapped per sport within the 100-request/day limit.

## Recommended use in dashboard commentary

- If `phase_confidence` is `high` or `medium`, the generator can use season-phase language.
- If `phase_confidence` is `low`, phrase cautiously: "the available calendar suggests..." or omit phase-specific claims.
- Use `warnings` to suppress unsupported/uncertain leagues.
- For Contextual Notes, require `source_url` and prefer `relevance` tags that match the section.

## Future additions Horatio recommends

1. `data/contextual-notes-candidates.json`: curated, source-backed candidate notes ready for Cowork to adapt.
2. X/social trend layer for player/team/league spikes, clearly separated from factual schedule/results data.
3. Competitor and retail-watch feeds: Nike, Adidas, Lids, Dick's, league shops, collectible launches.
4. More precise standings/results once we tune API request budget per league.
