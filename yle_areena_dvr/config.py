from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from pathlib import Path

class Settings(BaseSettings):
    yle_app_id: str | None = Field(None, validation_alias="YLE_APP_ID")
    yle_app_key: str | None = Field(None, validation_alias="YLE_APP_KEY")
    tmdb_api_key: str | None = Field(None, validation_alias="TMDB_API_KEY")
    download_base_dir: str = Field("~/Downloads/YleAreena", validation_alias="DOWNLOAD_BASE_DIR")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

def load_yaml_config(config_path: str | Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
