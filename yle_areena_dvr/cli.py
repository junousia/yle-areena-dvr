import asyncio
import sys
from pydantic import Field
from pydantic_cli import run_and_exit, Cmd, FailedExecutionException, to_runner
from pathlib import Path
from .client import YleClient
from .downloader import YleDownloader
from .rating import TMDbClient, TMDbUnavailable
from .config import DEFAULT_CONFIG_PATH, Settings, load_yaml_config
from .models import Program
from .db import init_db, get_program, save_program, mark_existing_program_seen, search_programs_db, get_programs_missing_year

class SearchCmd(Cmd):
    """Search Yle Areena programs from local database"""
    query: str = Field("", description="The search query for programs")
    limit: int = Field(10, description="Maximum number of results to show")
    min_rating: float | None = Field(None, description="Filter results by minimum TMDb rating (0-10)")
    only_new: bool = Field(False, description="Show only programs added recently")
    only_expiring: bool = Field(False, description="Show only programs expiring soon")
    output_json: bool = Field(False, description="Output raw JSON for AI agents")

    async def run_async(self):
        await init_db()
        if not self.output_json:
            query_display = self.query if self.query else "all"
            print(f"Searching local database for: {query_display}...")
            
        programs = await search_programs_db(
            self.query, 
            self.limit, 
            self.min_rating,
            only_new=self.only_new,
            only_expiring=self.only_expiring
        )
        
        if self.output_json:
            import json
            print(json.dumps([p.model_dump(mode='json') for p in programs], indent=2))
            return
        
        if not programs:
            print("No programs found in local database. Try running 'scrape' first.")
            return

        for p in programs:
            rating_str = f"[TMDb: {p.tmdb_rating:.1f}]" if p.tmdb_rating else "[No Rating]"
            # Display 'MOVIE' instead of 'PROGRAM' for user clarity
            display_type = "MOVIE" if p.type == "program" else p.type.upper()
            type_str = f"[{display_type}]"
            date_info = ""
            if p.expires_at:
                date_info += f" [Expires: {p.expires_at.strftime('%d.%m.%Y')}]"
            if p.published_at:
                date_info += f" [Published: {p.published_at.strftime('%d.%m.%Y')}]"
                
            print(f"- {type_str} {p.title} {rating_str}{date_info} (ID: {p.id})")
            if p.description:
                print(f"  {p.description}")

    def run(self):
        asyncio.run(self.run_async())


class DownloadCmd(Cmd):
    """Download a program by ID"""
    id: str = Field(..., description="The Yle Areena program ID (e.g., 1-1234567)")
    config_path: Path = Field(DEFAULT_CONFIG_PATH, description="Path to the config.yaml file")
    naming_preset: str | None = Field(None, description="Naming preset key from config naming.presets")
    output_template: str | None = Field(None, description="Custom yt-dlp output template (overrides preset)")
    dry_run: bool = Field(False, description="Print resolved output template/path without downloading")
    output_json: bool = Field(False, description="Output result as JSON")

    async def run_async(self):
        settings = Settings()
        yaml_config = load_yaml_config(self.config_path)
        yle = YleClient(app_id=settings.yle_app_id, app_key=settings.yle_app_key)

        existing = await get_program(self.id)
        tmdb = TMDbClient(api_key=settings.tmdb_api_key) if settings.tmdb_api_key else None

        # Yle item details endpoint is flaky for some IDs; fallback to DB/direct URL.
        try:
            program_details = await yle.get_program_details(self.id)
            title = program_details.title.fi or program_details.title.sv or program_details.title.en or (existing.title if existing else self.id)
            media_type = program_details.type
            pid = program_details.id
        except Exception:
            title = existing.title if existing else self.id
            media_type = existing.type if existing else "program"
            pid = self.id

        tmdb_match = None
        if tmdb:
            try:
                tmdb_match = await tmdb.get_match(title, media_type=media_type)
            except TMDbUnavailable:
                pass
        tmdb_year = tmdb_match.get("year") if tmdb_match else None

        program = Program(
            id=pid,
            title=title,
            type=media_type,
            url=f"https://areena.yle.fi/{pid}",
            year=tmdb_year or (existing.year if existing else None),
            tmdb_rating=(tmdb_match.get("rating") if tmdb_match else (existing.tmdb_rating if existing else None))
        )
        
        base_dir = yaml_config.get("download", {}).get("base_directory") or settings.download_base_dir
        downloader = YleDownloader(
            base_dir=base_dir,
            config=yaml_config
        )
        
        if not self.output_json:
            print(f"Starting download: {title} (ID: {program.id}, Type: {program.type}, Year: {program.year})")
        success = await downloader.download_program(
            program,
            naming_preset=self.naming_preset,
            output_template=self.output_template,
            dry_run=self.dry_run
        )
        if self.output_json:
            import json
            print(json.dumps({
                "ok": success,
                "id": program.id,
                "title": program.title,
                "year": program.year,
                "naming_preset": self.naming_preset,
                "output_template": self.output_template,
                "dry_run": self.dry_run
            }, indent=2))
            return
        if success:
            print(f"Successfully {'planned' if self.dry_run else 'downloaded'}: {title}")
        else:
            print(f"Failed to download: {title}")

    def run(self):
        asyncio.run(self.run_async())


class ScrapeCmd(Cmd):
    """Scrape a curated list page from Yle Areena"""
    url: str = Field("https://areena.yle.fi/tv/ohjelmat/57-1BbXLDz6v", description="The Areena list page URL to scrape")
    min_rating: float | None = Field(None, description="Filter results by minimum TMDb rating (0-10)")

    async def run_async(self):
        await init_db()
        settings = Settings()
        yle = YleClient(app_id=settings.yle_app_id, app_key=settings.yle_app_key)
        tmdb = TMDbClient(api_key=settings.tmdb_api_key) if settings.tmdb_api_key else None
        
        print(f"Scraping Areena page: {self.url}...")
        lists = await yle.scrape_areena_page(self.url)
        
        if not lists:
            print("No lists found.")
            return
            
        for list_title, programs in lists.items():
            print(f"\n=== {list_title} ===")
            for p in programs:
                existing_program = await get_program(p.id)
                
                is_new = False
                if existing_program:
                    rating = existing_program.tmdb_rating
                    await mark_existing_program_seen(p.id)
                else:
                    is_new = True
                    tmdb_match = None
                    if tmdb:
                        try:
                            tmdb_match = await tmdb.get_match(p.title, media_type=p.type)
                        except TMDbUnavailable:
                            pass
                    rating = tmdb_match.get("rating") if tmdb_match else None
                    if tmdb_match and tmdb_match.get("year"):
                        p.year = tmdb_match.get("year")
                    await save_program(p, rating)
                
                if self.min_rating and (rating is None or rating < self.min_rating):
                    continue
                    
                status_tag = "[NEW]" if is_new else "[EXISTING]"
                rating_str = f"[TMDb: {rating:.1f}]" if rating else "[No Rating]"
                display_type = "MOVIE" if p.type == "program" else p.type.upper()
                type_tag = f"[{display_type}]"
                
                print(f"- {status_tag} {type_tag} {p.title} {rating_str} (ID: {p.id})")
                if p.description:
                    print(f"  {p.description}")

    def run(self):
        asyncio.run(self.run_async())


class DetailsCmd(Cmd):
    """Fetch full TMDb detail (overview, genres, cast, runtime) for a title, for judging suitability"""
    id: str | None = Field(None, description="Areena program ID already in the local DB (e.g., 1-1234567)")
    title: str | None = Field(None, description="Title to search on TMDb (used if --id is not given, or not found)")
    year: int | None = Field(None, description="Release/first-air year to disambiguate the TMDb search")
    type: str = Field("program", description="Media type: 'program' (movie) or 'series'")
    output_json: bool = Field(True, description="Output raw JSON for AI agents")

    async def run_async(self):
        settings = Settings()
        if not settings.tmdb_api_key:
            msg = "TMDB_API_KEY missing"
            if self.output_json:
                import json
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(f"Error: {msg}")
            return

        title = self.title
        year = self.year
        media_type = self.type

        if self.id:
            existing = await get_program(self.id)
            if existing:
                title = title or existing.title
                year = year or existing.year
                media_type = existing.type
            elif not title:
                msg = f"No local record for id={self.id}; pass --title to search TMDb directly"
                if self.output_json:
                    import json
                    print(json.dumps({"ok": False, "error": msg}, indent=2))
                else:
                    print(f"Error: {msg}")
                return

        if not title:
            msg = "Provide --id (in local DB) or --title"
            if self.output_json:
                import json
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(f"Error: {msg}")
            return

        tmdb = TMDbClient(api_key=settings.tmdb_api_key)
        try:
            details = await tmdb.search_details(title, year=year, media_type=media_type)
        except TMDbUnavailable as e:
            msg = f"TMDb unreachable, try again: {e}"
            if self.output_json:
                import json
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(f"Error: {msg}")
            return

        if self.output_json:
            import json
            if not details:
                print(json.dumps({"ok": False, "error": f"No TMDb match for '{title}'"}, indent=2))
                return
            print(json.dumps({"ok": True, **details}, indent=2))
            return

        if not details:
            print(f"No TMDb match found for '{title}'.")
            return

        print(f"{details['title']} ({details.get('year') or 'unknown year'}) [{details.get('media_type')}]")
        if details.get("tagline"):
            print(f"  \"{details['tagline']}\"")
        if details.get("genres"):
            print(f"  Genres: {', '.join(details['genres'])}")
        if details.get("runtime_minutes"):
            print(f"  Runtime: {details['runtime_minutes']} min")
        if details.get("vote_average"):
            print(f"  TMDb: {details['vote_average']:.1f} ({details.get('vote_count') or 0} votes)")
        if details.get("directors"):
            print(f"  Director(s): {', '.join(details['directors'])}")
        if details.get("cast"):
            print(f"  Cast: {', '.join(details['cast'])}")
        if details.get("overview"):
            print(f"  {details['overview']}")

    def run(self):
        asyncio.run(self.run_async())


class NamingCmd(Cmd):
    """List configured naming presets"""
    config_path: Path = Field(DEFAULT_CONFIG_PATH, description="Path to the config.yaml file")
    output_json: bool = Field(False, description="Output raw JSON")

    def run(self):
        cfg = load_yaml_config(self.config_path)
        presets = cfg.get("naming", {}).get("presets", {})
        if self.output_json:
            import json
            print(json.dumps(presets, indent=2))
            return
        if not presets:
            print("No naming presets configured.")
            return
        print("Naming presets:")
        for k, v in presets.items():
            print(f"- {k}: {v}")


class BackfillYearsCmd(Cmd):
    """Backfill missing years from TMDb for programs in local DB"""
    limit: int = Field(200, description="Max programs to process")
    output_json: bool = Field(False, description="Output JSON summary")

    async def run_async(self):
        await init_db()
        settings = Settings()
        if not settings.tmdb_api_key:
            msg = "TMDB_API_KEY missing"
            if self.output_json:
                import json
                print(json.dumps({"ok": False, "error": msg}, indent=2))
                return
            print(f"Error: {msg}")
            return

        tmdb = TMDbClient(api_key=settings.tmdb_api_key)
        programs = await get_programs_missing_year(limit=self.limit)
        updated = 0
        unavailable = 0

        for p in programs:
            try:
                m = await tmdb.get_match(p.title, media_type=p.type)
            except TMDbUnavailable:
                unavailable += 1
                continue
            if m and m.get("year"):
                p.year = m.get("year")
                await save_program(p, p.tmdb_rating)
                updated += 1

        if self.output_json:
            import json
            print(json.dumps({"ok": True, "scanned": len(programs), "updated": updated, "tmdb_unavailable": unavailable}, indent=2))
        else:
            print(f"Backfill done. scanned={len(programs)} updated={updated} tmdb_unavailable={unavailable}")

    def run(self):
        asyncio.run(self.run_async())


def exception_handler(e: BaseException) -> int:
    """Custom exception handler to provide clean error messages."""
    if isinstance(e, FailedExecutionException):
        msg = str(e.message)
        if "error: " in msg:
            msg = msg.split("error: ")[-1]
            
        if "unrecognized arguments" in msg:
            print(f"Error: {msg}", file=sys.stderr)
            print("\nAvailable subcommands: search, download, scrape, details, naming, backfill-years", file=sys.stderr)
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return e.exit_code
    
    print(f"Error: {e}", file=sys.stderr)
    return 1

def main():
    # pydantic-cli (especially version 10.0.0) requires explicit boolean values.
    # To support flags without values, we preprocess sys.argv.
    bool_flags = ["--output_json", "--only_new", "--only_expiring", "--dry_run"]
    
    alias_map = {
        "--json": "--output_json",
        "--naming-preset": "--naming_preset",
        "--output-template": "--output_template",
        "--dry-run": "--dry_run",
        "--min-rating": "--min_rating",
        "--only-new": "--only_new",
        "--only-expiring": "--only_expiring",
    }

    new_argv = []
    i = 0
    while i < len(sys.argv):
        arg = alias_map.get(sys.argv[i], sys.argv[i])
        new_argv.append(arg)
        if arg in bool_flags:
            # Check if next arg is already a boolean value
            if i + 1 < len(sys.argv) and sys.argv[i+1].lower() in ["true", "false", "1", "0", "yes", "no"]:
                pass
            else:
                # Append default true for flag presence
                new_argv.append("true")
        i += 1
    
    sys.argv = new_argv

    subcommands = {
        "search": SearchCmd,
        "download": DownloadCmd,
        "scrape": ScrapeCmd,
        "details": DetailsCmd,
        "naming": NamingCmd,
        "backfill-years": BackfillYearsCmd,
    }
    
    runner = to_runner(subcommands, description="Yle Areena DVR CLI", exception_handler=exception_handler)

    # Friendly behavior when no subcommand is provided
    if len(sys.argv) <= 1:
        try:
            return runner(["--help"])
        except Exception:
            print("Usage: yle-dvr {search|download|scrape|naming|backfill-years} [options]")
            return 0

    sys.exit(runner(sys.argv[1:]))

if __name__ == "__main__":
    main()
