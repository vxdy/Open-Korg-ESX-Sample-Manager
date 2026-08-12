"""Vector icon helper built on qtawesome (Font Awesome 6), used instead of
the platform's built-in QStyle icons so every icon in the app matches the
same flat, dark-theme-friendly style regardless of OS/theme."""

import qtawesome as qta

from ui.theme import TEXT, TEXT_DIM, ACCENT


def icon(name: str, color: str = TEXT) -> "qta.icon":
    """Look up a Font Awesome Solid icon by its short name, e.g. icon('trash')
    resolves to 'fa6s.trash'. Colored to match the app's dark theme by default."""
    return qta.icon(f"fa6s.{name}", color=color)


def dim_icon(name: str) -> "qta.icon":
    return icon(name, color=TEXT_DIM)


def accent_icon(name: str) -> "qta.icon":
    return icon(name, color=ACCENT)
