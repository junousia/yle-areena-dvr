# Yle Areena DVR

A Python tool for searching, scraping, and downloading movies and series from Yle Areena with integrated TMDb ratings and flexible naming templates.

## Features
- **Yle Areena Search**: Find movies by query or category.
- **Scrape Curated Lists**: Extract movies directly from Areena's curated lists (e.g., "Katsotuimmat leffat").
- **TMDb Ratings**: Automatically fetch and filter by TMDb ratings (The Movie Database). Excellent multi-language support.
- **yt-dlp Integration**: High-quality downloads with subtitle support.
- **Flexible Organization**: Customize your folder structure and file naming via `config.yaml`.
- **Modern Python**: Built with Python 3.12+, Pydantic 2, and managed entirely with `uv`.

## Installation

This project is built using `uv`, an extremely fast Python package and project manager.

```bash
# Clone the repository
git clone https://github.com/junousia/yle-areena-dvr.git
cd yle-areena-dvr

# Sync the environment
uv sync

# Or install it globally as a tool
uv tool install .
```

Or run it straight from PyPI without installing anything:

```bash
uvx yle-areena-dvr --help      # also available under the short name `yle-dvr`
```

## Setup

1. Copy `.env.template` to `.env`:
   ```bash
   cp .env.template .env
   ```
2. Fill in your `TMDB_API_KEY` (free from themoviedb.org). `YLE_APP_ID` and `YLE_APP_KEY` are **optional**: by default the tool reads the keys that Areena's own web frontend embeds in its pages at runtime; set them only to override that.
3. Customize `assets/config.yaml` to change where your movies are saved.

## Usage

If you installed it via `uv tool install .`, you can run `yle-dvr` directly. Otherwise, use `uv run yle-dvr` inside the project directory.

### Search for Programs
```bash
uv run yle-dvr search --query "Metsolat" --limit 5 --min-rating 7.0

# Search for expiring programs
uv run yle-dvr search --only-expiring

# Search for recently added programs
uv run yle-dvr search --only-new

# You can also get machine-readable output for AI agents:
uv run yle-dvr search --query "Action" --json
```

### Scrape Curated Lists (Movies or Series)
```bash
# Scrape movies
uv run yle-dvr scrape --url "https://areena.yle.fi/tv/ohjelmat/57-1BbXLDz6v" --min-rating 7.5

# Scrape series
uv run yle-dvr scrape --url "https://areena.yle.fi/tv/ohjelmat/57-p8JeXvBA0"
```

### Download a Program (Movie or Series)
```bash
uv run yle-dvr download --id "1-2345678"
```

### Look Up Full Details for Suitability (Overview, Genres, Cast)
```bash
# From a program already in the local DB
uv run yle-dvr details --id "1-2345678" --json

# Directly by title, no DB entry required
uv run yle-dvr details --title "Fight Club" --year 1999 --json
```

## Configuration
See `assets/config.yaml` for customization options including folder templates and subtitle preferences.

## Disclaimer

This is an unofficial tool and is not affiliated with Yle. Downloading is intended for personal use of content that Yle makes available to you; respect Yle's terms of service and applicable copyright law. You are responsible for how you use it.

## Use as an agent skill

`SKILL.md` makes this repo usable as a skill in [Hermes Agent](https://hermes-agent.nousresearch.com) and OpenClaw.
Clone it into the agent's skills directory (for Hermes e.g. `~/.hermes/skills/<category>/yle-areena-dvr`,
for OpenClaw `<workspace>/skills/yle-areena-dvr`), run `uv sync` there, and copy `.env.template` to `.env`.
Python 3.12-3.14 is required (3.13 is tested).

## License

MIT, see [LICENSE](LICENSE).
