# Fanatics CBO Dashboard Signals

Public JSON feed for external sports/context signals consumed by Claude Cowork and the Fanatics CBO executive dashboard workflow.

## Raw URLs for consumers

- `sports-facts.json`: https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data/sports-facts.json
- `sports-events.json`: https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data/sports-events.json
- `contextual-notes-candidates.json`: https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data/contextual-notes-candidates.json
- `manifest.json`: https://raw.githubusercontent.com/nathanegamble/fanatics-cbo-dashboard-signals/main/data/manifest.json

## Files

### `data/sports-facts.json`

Structured league facts from API-Sports plus documented fallbacks where API-Sports coverage is incomplete. This file includes Cowork's requested `season_phase` field and adds explanation fields:

- `season_phase`: `off-season`, `pre-season`, `in-season`, `post-season`, or `unknown`
- `phase_detail`: more specific value such as `regular-season`, `playoffs`, `spring-training`, `off-season`
- `phase_basis`: plain-English explanation of how the phase was derived
- `phase_confidence`: `high`, `medium`, or `low`

Covered v0.1 leagues:

- NFL
- NCAA Football
- MLB
- NBA
- WNBA (fallback calendar until API coverage is confirmed)
- NCAA Basketball
- NCAA Women's Basketball
- NHL
- MLS
- FIFA World Cup

### `data/sports-events.json`

Sourced public sports-news items grouped into Cowork's requested windows:

- `yesterday`
- `today`
- `this_week`
- `this_month`
- `next_month`

Each window is represented as:

```json
{
  "window_start": "YYYY-MM-DD",
  "window_end": "YYYY-MM-DD",
  "items": []
}
```

Each item includes a `source_url`, `source_name`, `league`, `confidence`, and relevance tags. v0.1 uses public ESPN RSS feeds for reliable automation and source URLs. The Yahoo Scout/browser path requested by Cowork is documented as a POC path to validate next; it can publish into the same schema without changing consumer code.

### `data/contextual-notes-candidates.json`

A bridge layer derived from `sports-facts.json` and `sports-events.json`. These are **candidate** Contextual Notes for Cowork to adapt, not final executive copy.

Each candidate includes:

- `topic`
- `league`
- `note_type`
- `dashboard_slots`
- `summary`
- `why_it_matters`
- `supporting_facts`
- `suggested_copy`
- `confidence`
- `sources`
- `warnings`

Dashboard slot hints currently include values such as `today_read`, `league_momentum`, `bigger_picture`, `what_moving`, `creative_programs`, and `structural_signals`.

### `data/manifest.json`

Small status/index file for consumers that want to check freshness and file status before reading the full payloads.

## Status values

Top-level `status` values:

- `ok`: collection completed without warnings
- `partial`: usable data was produced, but with warnings/coverage gaps
- `error`: output is not safe to consume as fresh data

Consumers should treat `partial` as usable but inspect `warnings`.

## Season phase derivation

API-Sports does not expose one universal season-phase field across all sports. This repo derives it from:

1. API-Sports season start/end windows.
2. API-Sports `current` flags where present.
3. Separate preseason/training competitions where available, e.g. MLB Spring Training.
4. Recent/scheduled game metadata containing playoff/final/preseason markers.
5. Documented fallback calendars for coverage gaps such as WNBA.

The derivation is intentionally transparent via `phase_basis` and `phase_confidence`.

## Security / public-data guardrails

- Do not commit API keys, tokens, credentials, private dashboard data, or personal data.
- Public outputs should contain only public sports facts/news references.
- Scripts read `API_SPORTS_KEY` from the local environment or Hermes `.env`.
- Validation checks for obvious secret-like strings before commit.

## Local run

```bash
python3 scripts/refresh_all.py
python3 scripts/validate_outputs.py
```

## Commit cadence

Daily refresh target: before 7am ET, with commit message like:

```text
chore(signals): refresh YYYY-MM-DD
```

## Notes for Claude Cowork

Recommended consumption pattern:

1. Fetch `manifest.json` first.
2. If `status` is `ok` or `partial`, fetch `sports-facts.json` and `sports-events.json`.
3. Use `phase_basis`, `phase_confidence`, and `warnings` to avoid overclaiming uncertain seasonality.
4. Use `contextual-notes-candidates.json` as a shortlist of source-backed note ideas; adapt tone and placement rather than copying blindly.
5. For Contextual Notes, prefer candidates/events with `confidence: high|medium`, a valid source URL, and dashboard slots matching the target section.
