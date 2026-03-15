"""
SolarWatch Constants & Enumerations
====================================
All enums and constants used across the project.
These enums are used both in SQLAlchemy models and in validation logic.
"""
from __future__ import annotations

import enum
from typing import Dict, List, Set


# ─── Data Source ────────────────────────────────────────────

class SourcePlatform(enum.Enum):
    """Review data source platform."""
    GOOGLE_PLAY = "google_play"
    APP_STORE = "app_store"


# ─── 4+1 Analysis Framework ────────────────────────────────

class PrimaryCategory(enum.Enum):
    """
    The "4+1" vertical analysis framework.

    - Commissioning: Installation, device pairing, WiFi/network setup
    - O&M:           Operations & Maintenance, monitoring, alerts, diagnostics
    - Localization:  Multi-language, regional compliance, grid codes
    - DevOps:        App crashes, performance, version regressions, UI bugs
    - Ecosystem:     Battery, EV charger, third-party device integration
    """
    COMMISSIONING = "Commissioning"
    O_AND_M = "O&M"
    LOCALIZATION = "Localization"
    DEVOPS = "DevOps"
    ECOSYSTEM = "Ecosystem"


# ─── User Persona ──────────────────────────────────────────

class UserPersona(enum.Enum):
    """
    Distinguish B2B (Installer) vs B2C (Homeowner) feedback.

    Reason: Homeowner noise ("ugly UI") drowns out installer pain points
    ("network configuration timeout"). We need to filter for B2B hardcore feedback.
    """
    INSTALLER = "Installer"
    HOMEOWNER = "Homeowner"


# ─── Impact Severity ───────────────────────────────────────

class ImpactSeverity(enum.Enum):
    """
    Issue severity weighting.

    - Critical: System down, data loss, inverter offline (weight: 3)
    - Major:    Core feature broken, cannot add device (weight: 2)
    - Minor:    UI complaints, slow loading, cosmetic (weight: 1)
    """
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"


# ─── Severity Weights (for Severity-Adjusted Score) ────────

SEVERITY_WEIGHTS: Dict[ImpactSeverity, int] = {
    ImpactSeverity.CRITICAL: 3,
    ImpactSeverity.MAJOR: 2,
    ImpactSeverity.MINOR: 1,
}


# ─── Team Classification ──────────────────────────────────

class Team(enum.Enum):
    """Red vs Blue competitive framework."""
    RED = "red"
    BLUE = "blue"


# ─── Region Aggregation ───────────────────────────────────

REGION_GROUPS: Dict[str, List[str]] = {
    "DACH": ["DE", "AT", "CH"],
    "South Europe": ["IT", "ES"],
    "Emerging": ["PL", "RO"],
}

ALL_REGIONS: List[str] = ["DE", "AT", "CH", "IT", "ES", "PL", "RO"]


# ─── Valid Enum Values (for LLM response validation) ──────

VALID_CATEGORIES: Set[str] = set(c.value for c in PrimaryCategory)
VALID_PERSONAS: Set[str] = set(p.value for p in UserPersona)
VALID_SEVERITIES: Set[str] = set(s.value for s in ImpactSeverity)


# ─── Region → Language Mapping ────────────────────────────
# CRITICAL: AT and CH speak German, NOT "austrian" or "swiss".
# Google Play's `lang` parameter requires the actual language code.

REGION_LANG_MAP: Dict[str, str] = {
    "DE": "de",
    "AT": "de",  # Austria → German
    "CH": "de",  # Switzerland → German (dominant PV market language)
    "IT": "it",
    "ES": "es",
    "PL": "pl",
    "RO": "ro",
}
