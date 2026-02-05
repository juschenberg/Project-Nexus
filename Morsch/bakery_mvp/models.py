"""Model-Konstanten und Validierung für die Bäckerei-CLI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

WEEKDAYS: List[str] = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
PREF_VALUES: List[str] = ["no", "yes", "prefer"]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str = ""


def normalize_pref(value: str) -> Optional[str]:
    """Normalisiert Eingaben für Präferenzen. Gibt None bei leerer Eingabe zurück."""
    if value is None:
        return None
    val = value.strip().lower()
    if val == "":
        return None
    if val in PREF_VALUES:
        return val
    return "__invalid__"


def validate_pref(value: str) -> ValidationResult:
    """Validiert einen Präferenzwert."""
    if value in PREF_VALUES:
        return ValidationResult(True, "")
    return ValidationResult(False, f"Ungültiger Wert: '{value}'. Erlaubt: no/yes/prefer")


def validate_name(name: str) -> ValidationResult:
    """Validiert einen Mitarbeiternamen."""
    if name is None:
        return ValidationResult(False, "Name darf nicht leer sein.")
    if len(name.strip()) < 2:
        return ValidationResult(False, "Name muss mindestens 2 Zeichen haben.")
    return ValidationResult(True, "")


def format_prefs_compact(prefs: Dict[str, str]) -> str:
    """Erzeugt eine kompakte Darstellung der Präferenzen."""
    parts: List[str] = []
    for day in WEEKDAYS:
        parts.append(f"{day}:{prefs.get(day, '-')}")
    return ", ".join(parts)


def parse_filter_day(value: str) -> Optional[str]:
    """Parst einen Wochentag (Deutsch)."""
    if value is None:
        return None
    val = value.strip().title()
    if val in WEEKDAYS:
        return val
    return None


def parse_filter_pref(value: str) -> Optional[str]:
    """Parst eine Präferenz für Filter (no/yes/prefer)."""
    if value is None:
        return None
    val = value.strip().lower()
    if val in PREF_VALUES:
        return val
    return None
