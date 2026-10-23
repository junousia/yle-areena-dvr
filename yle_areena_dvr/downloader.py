import yt_dlp
import os
import asyncio
from .models import Program

class YleDownloader:
    def __init__(self, base_dir: str, config: dict):
        self.base_dir = os.path.expanduser(base_dir)
        self.config = config

    def _resolve_filename(self, program: Program, naming_preset: str | None = None, output_template: str | None = None) -> str:
        naming = self.config.get("naming", {})
        if output_template:
            return output_template
        if naming_preset:
            preset = naming.get("presets", {}).get(naming_preset)
            if preset:
                return preset.format(title=program.title, year=program.year or "Unknown")
        if program.type == "series":
            return naming.get("series_filename", "{title} - S{season_number}E{episode_number} - {episode_title}.%(ext)s").replace("{title}", program.title)
        return naming.get("movie_filename", "{title} ({year}).%(ext)s").format(
            title=program.title,
            year=program.year or "Unknown"
        )

    def _sync_download(self, program: Program, download_path: str | None, naming_preset: str | None = None, output_template: str | None = None, dry_run: bool = False) -> bool:
        """Synchronous wrapper for yt-dlp."""
        if download_path is None:
            if program.type == "series":
                folder_template = self.config.get("naming", {}).get("series_folder", "TV Shows/{title}")
            else:
                folder_template = self.config.get("naming", {}).get("movie_folder", "Movies/{title} ({year})")
            
            folder_name = folder_template.format(
                title=program.title,
                year=program.year or "Unknown",
                id=program.id
            )
            download_path = os.path.join(self.base_dir, folder_name)

        os.makedirs(download_path, exist_ok=True)

        filename = self._resolve_filename(program, naming_preset=naming_preset, output_template=output_template)

        ydl_opts = {
            'outtmpl': os.path.join(download_path, filename),
            'format': self.config.get("download", {}).get("format", "bv*+ba/b"),
            'merge_output_format': self.config.get("download", {}).get("merge_output_format", "mkv"),
            'writesubtitles': self.config.get("download", {}).get("subtitles", {}).get("enabled", True),
            'subtitleslangs': self.config.get("download", {}).get("subtitles", {}).get("languages", ["fi", "sv", "en"]),
            'logger': None,
            'progress_hooks': [],
        }

        if dry_run:
            print(f"DRY_RUN outtmpl={ydl_opts['outtmpl']}")
            print(f"DRY_RUN url={program.url}")
            return True

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([program.url])
                return True
            except Exception as e:
                print(f"Error downloading {program.title}: {e}")
                return False

    async def download_program(
        self,
        program: Program,
        download_path: str | None = None,
        naming_preset: str | None = None,
        output_template: str | None = None,
        dry_run: bool = False
    ) -> bool:
        """Asynchronously downloads a program using yt-dlp."""
        return await asyncio.to_thread(self._sync_download, program, download_path, naming_preset, output_template, dry_run)
