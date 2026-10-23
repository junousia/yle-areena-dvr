---
name: yle-areena-dvr
description: Search, scrape, enrich (TMDb), and download Yle Areena movies/series with Plex-friendly naming and local DB workflows.
---

# Yle Areena DVR Skill

Use `uv run yle-dvr ...`.

## Core commands

- `search` → query local DB
- `scrape` → scrape Areena list page into DB (+ TMDb enrich)
- `details` → fetch full TMDb detail (overview, genres, cast, runtime) for one title, to judge suitability
- `download` → download by Areena ID
- `naming` → list naming presets
- `backfill-years` → fill missing DB years from TMDb

## Judging suitability with `details`

`search`/`scrape` only carry a title, TMDb rating, and year — not enough to judge whether a movie
is actually a good fit. Before recommending or auto-downloading something, look it up:

```bash
# By Areena ID already in the local DB
uv run yle-dvr details --id "1-70111573" --json

# By title directly (no DB entry needed)
uv run yle-dvr details --title "Fight Club" --year 1999 --json

# Series (default type is "program", i.e. movie)
uv run yle-dvr details --title "Breaking Bad" --type series --json
```

Returns `overview` (plot summary), `genres`, `cast`, `directors`, `runtime_minutes`, `tagline`,
`vote_average`/`vote_count`, and `keywords` — enough to actually reason about whether a title
matches what the user wants, instead of guessing from the title alone.

If TMDb is unreachable (network blip), the response is `{"ok": false, "error": "TMDb unreachable, try again: ..."}` —
distinct from `{"ok": false, "error": "No TMDb match for '<title>'"}`, which means it genuinely isn't
on TMDb. Retry on the former; don't treat it as "not found".

## Key improvements

- TMDb year support in DB + download path
- Backfill command for existing records in DB
- Naming preset support and custom output templates in CLI
- JSON output on all key commands

## Examples

```bash
# Scrape list and enrich with TMDb
uv run yle-dvr scrape --url "https://areena.yle.fi/tv/ohjelmat/57-1BbXLDz6v"

# Search DB
uv run yle-dvr search --query "Three Billboards" --json

# Show naming presets
uv run yle-dvr naming

# Download with preset naming
uv run yle-dvr download --id "1-70111573" --naming-preset "plex-movie"

# Download with explicit output template
uv run yle-dvr download --id "1-70111573" --output-template "{title} ({year}) [YLE].%(ext)s"

# Dry run (resolve naming/path without downloading)
uv run yle-dvr download --id "1-70111573" --naming-preset "plex-movie" --dry-run

# Backfill missing years from TMDb for existing DB rows
uv run yle-dvr backfill-years --limit 500
```

## Naming format

Configured in `assets/config.yaml` under `naming`:

- `movie_filename`
- `series_filename`
- `presets` (e.g. `plex-movie`, `plex-series`)

Download precedence:

1. `--output-template`
2. `--naming-preset`
3. Default `movie_filename` / `series_filename`

## TMDb requirement

Set `TMDB_API_KEY` in `.env` to enable TMDb year/rating enrichment and backfill.

Without TMDb key, backfill is skipped and year enrichment is limited.
