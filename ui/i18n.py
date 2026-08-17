"""Minimal JSON-backed translation layer. Every user-facing string in the
app is looked up by a dotted key (e.g. "tab_patterns.copy_pattern") via
tr(key); the actual English/German text lives in ui/locales/<lang>.json,
not in the Python source, so adding a language is just adding a JSON file.

The active language is chosen once at startup (see main.py) and stays
fixed for the lifetime of the process - switching languages at runtime
requires a restart, since the app builds large parts of its UI (esp. the
Steps tab's dynamically-rebuilt tables) directly from tr() calls rather
than through a Qt retranslateUi()-style mechanism that could re-run them
in place."""

import json
import os
import sys

from PyQt6.QtCore import QLocale, QSettings

DEFAULT_LANGUAGE = "en"
AVAILABLE_LANGUAGES = {"en": "English", "de": "Deutsch"}

_strings = {}
_fallback_strings = {}
_current_language = DEFAULT_LANGUAGE


def _locales_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "locales")
    return os.path.join(base, "ui", "locales")


def _load(lang: str) -> dict:
    path = os.path.join(_locales_dir(), f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def set_language(lang: str) -> None:
    """Loads `lang`'s strings (falling back to DEFAULT_LANGUAGE's file for
    any key the chosen language doesn't have yet, so a partially-translated
    locale never shows a raw key instead of at least the English text)."""
    global _strings, _fallback_strings, _current_language
    if lang not in AVAILABLE_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    _current_language = lang
    _fallback_strings = _load(DEFAULT_LANGUAGE)
    _strings = _fallback_strings if lang == DEFAULT_LANGUAGE else _load(lang)


def current_language() -> str:
    return _current_language


def tr(key: str, **kwargs) -> str:
    """Looks up `key` in the active language, falling back to English, then
    to the key itself (a visible, greppable marker that a translation is
    missing, rather than a crash). kwargs are applied with str.format for
    strings with placeholders, e.g. tr("x.count", n=3)."""
    text = _strings.get(key)
    if text is None:
        text = _fallback_strings.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def _detect_system_language() -> str:
    lang = QLocale.system().name().split("_")[0].lower()
    return lang if lang in AVAILABLE_LANGUAGES else DEFAULT_LANGUAGE


def load_saved_language() -> str:
    """The persisted choice (see save_language) if there is one, otherwise
    a best guess from the OS locale, so a German-Windows user sees German
    on first launch without having to find the setting first."""
    saved = QSettings().value("language", None, type=str)
    if saved in AVAILABLE_LANGUAGES:
        return saved
    return _detect_system_language()


def save_language(lang: str) -> None:
    QSettings().setValue("language", lang)


set_language(DEFAULT_LANGUAGE)
