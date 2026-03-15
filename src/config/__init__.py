"""SolarWatch Config Package."""
from src.config.settings import load_settings, Settings
from src.config.constants import (
    SourcePlatform,
    PrimaryCategory,
    UserPersona,
    ImpactSeverity,
    Team,
    SEVERITY_WEIGHTS,
    REGION_GROUPS,
    REGION_LANG_MAP,
    ALL_REGIONS,
    VALID_CATEGORIES,
    VALID_PERSONAS,
    VALID_SEVERITIES,
)

__all__ = [
    "load_settings",
    "Settings",
    "SourcePlatform",
    "PrimaryCategory",
    "UserPersona",
    "ImpactSeverity",
    "Team",
    "SEVERITY_WEIGHTS",
    "REGION_GROUPS",
    "REGION_LANG_MAP",
    "ALL_REGIONS",
    "VALID_CATEGORIES",
    "VALID_PERSONAS",
    "VALID_SEVERITIES",
]
