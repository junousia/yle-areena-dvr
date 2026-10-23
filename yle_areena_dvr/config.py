from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from importlib import resources
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("assets/config.yaml")

class Settings(BaseSettings):
    yle_app_id: str | None = Field(None, validation_alias="YLE_APP_ID")
    yle_app_key: str | None = Field(None, validation_alias="YLE_APP_KEY")
    tmdb_api_key: str | None = Field(None, validation_alias="TMDB_API_KEY")
    download_base_dir: str = Field("~/Downloads/YleAreena", validation_alias="DOWNLOAD_BASE_DIR")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

def load_yaml_config(config_path: str | Path) -> dict:
    """Loads the YAML config; falls back to the default bundled in the package when the
    default ``assets/config.yaml`` does not exist (e.g. when installed from PyPI)."""
    path = Path(config_path)
    if not path.exists() and path == DEFAULT_CONFIG_PATH:
        text = resources.files("yle_areena_dvr").joinpath("default_config.yaml").read_text(encoding="utf-8")
        return yaml.safe_load(text)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
