"""CampusPulse configuration and settings module.
Loads environment variables and sets up project-wide configuration.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Postgres configuration
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "campuspulse_db"
    postgres_user: str = "campuspulse"
    postgres_password: str = "campuspulse_secret"

    # Pipeline configuration
    log_level: str = "INFO"
    data_dir: Path = BASE_DIR / "data" / "sample"
    company_aliases_path: Path = BASE_DIR / "config" / "company_aliases.csv"
    validation_rules_path: Path = BASE_DIR / "config" / "validation_rules.yml"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URI."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()


def load_validation_rules() -> dict[str, Any]:
    """Load schema validation rules and constraints from YAML."""
    if not settings.validation_rules_path.exists():
        return {}
    with open(settings.validation_rules_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_company_aliases() -> dict[str, str]:
    """Load canonical company alias lookup mapping."""
    aliases: dict[str, str] = {}
    if not settings.company_aliases_path.exists():
        return aliases
    with open(settings.company_aliases_path, encoding="utf-8") as f:
        # Skip header
        lines = f.readlines()
        for line in lines[1:]:
            parts = line.strip().split(",", 1)
            if len(parts) == 2:
                alias, canonical = parts
                aliases[alias.strip().lower()] = canonical.strip()
    return aliases
