"""
SolarWatch Settings Loader
============================
Parses settings.yaml with Pydantic validation.
Provides type-safe access to all project configuration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ─── Sub-models ────────────────────────────────────────────

class ProjectConfig(BaseModel):
    """Top-level project metadata."""
    name: str = "SolarWatch"
    time_window_days: int = Field(default=180, ge=30, le=365)


class TargetApp(BaseModel):
    """A single monitoring target (app) definition."""
    name: str
    team: str = Field(pattern=r"^(red|blue)$")
    google_play_id: str
    app_store_id: str
    regions: list[str] = Field(min_length=1)

    @field_validator("regions", mode="before")
    @classmethod
    def validate_regions(cls, v: list[str]) -> list[str]:
        valid = {"DE", "AT", "CH", "IT", "ES", "PL", "RO"}
        for region in v:
            if region not in valid:
                raise ValueError(f"Invalid region: {region}. Valid: {valid}")
        return v


class LLMConfig(BaseModel):
    """LLM API configuration."""
    provider: str = Field(default="gemini", pattern=r"^(gemini|openai)$")
    model: str = "gemini-2.5-pro"
    batch_size: int = Field(default=50, ge=1, le=200)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_retries: int = Field(default=3, ge=1, le=10)


class DatabaseConfig(BaseModel):
    """Database configuration."""
    path: str = "data/solarwatch.db"

    @property
    def absolute_path(self) -> Path:
        """Resolve path relative to project root."""
        return Path(self.path).resolve()


class ScrapingConfig(BaseModel):
    """Scraping rate-limit and retry configuration."""
    rate_limit_google: float = Field(default=1.0, ge=0.1)
    rate_limit_appstore: float = Field(default=0.5, ge=0.1)
    max_retries: int = Field(default=3, ge=1, le=10)
    initial_lookback_days: int = Field(
        default=180, ge=1, le=365,
        description="Cold-start lookback window for first ingestion (days)"
    )


# ─── Root Settings ─────────────────────────────────────────

class Settings(BaseModel):
    """Root settings model — validated representation of settings.yaml."""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    targets: list[TargetApp] = Field(default_factory=list)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)

    @property
    def red_team_targets(self) -> list[TargetApp]:
        """Return Red Team (Huawei, Sungrow) targets."""
        return [t for t in self.targets if t.team == "red"]

    @property
    def blue_team_targets(self) -> list[TargetApp]:
        """Return Blue Team (SMA, Fronius, SolarEdge, Enphase) targets."""
        return [t for t in self.targets if t.team == "blue"]


# ─── Loader ────────────────────────────────────────────────

_DEFAULT_SETTINGS_PATH = Path(__file__).parent.parent.parent / "settings.yaml"
_cached_settings: Optional[Settings] = None


def load_settings(path: Path | str | None = None, reload: bool = False) -> Settings:
    """
    Load and validate settings from YAML file.

    Args:
        path:   Path to settings.yaml. Defaults to project root.
        reload: Force reload even if cached.

    Returns:
        Validated Settings instance.

    Raises:
        FileNotFoundError: If settings.yaml doesn't exist.
        pydantic.ValidationError: If YAML content is invalid.
    """
    global _cached_settings

    if _cached_settings is not None and not reload:
        return _cached_settings

    settings_path = Path(path) if path else _DEFAULT_SETTINGS_PATH

    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")

    with open(settings_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    _cached_settings = Settings.model_validate(raw)
    return _cached_settings
