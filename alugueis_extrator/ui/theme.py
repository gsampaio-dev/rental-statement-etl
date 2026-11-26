"""Colors, fonts and DPI helpers for the desktop interface."""

from __future__ import annotations

from dataclasses import dataclass
import sys
import tkinter as tk
import tkinter.font as tkfont


# Palette: light background, blue as the main action color, green for
# success and amber for review. The navy text color matches the project badge
# lettering so the brand and the interface read as one composition.
PAGE_BG = "#EEF2F7"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F6F8FB"
BORDER = "#D8E0EA"
BORDER_STRONG = "#C3CEDC"

TEXT = "#22344A"
TEXT_MUTED = "#5A6A7E"
TEXT_SUBTLE = "#7A8899"

PRIMARY = "#1F66C9"
PRIMARY_HOVER = "#1A58AF"
PRIMARY_PRESSED = "#154A94"
PRIMARY_DISABLED = "#B9CBE6"
PRIMARY_TINT = "#EDF3FC"
PRIMARY_TINT_BORDER = "#C9DAF3"
FOCUS = "#1F66C9"

SECONDARY_HOVER = "#EEF3FA"
SECONDARY_PRESSED = "#E1E9F5"

SUCCESS = "#1E8E4E"
SUCCESS_TEXT = "#14532D"
SUCCESS_BG = "#ECF7F0"
SUCCESS_BORDER = "#BCE3C9"

WARNING = "#D9820B"
WARNING_TEXT = "#6B4300"
WARNING_BG = "#FFF7E8"
WARNING_BORDER = "#F1D299"

DANGER = "#C93A3A"
DANGER_TEXT = "#7A1F1F"
DANGER_BG = "#FDEFEF"
DANGER_BORDER = "#F1C2C2"

PDF_RED = "#D23F31"
EXCEL_GREEN = "#1D7044"

ICON_FONT_CANDIDATES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

# Segoe MDL2 / Fluent glyph code points (system fonts on Windows 10/11).
GLYPH_FOLDER = "\ue8b7"
GLYPH_FOLDER_OPEN = "\ue838"
GLYPH_CALENDAR = "\ue787"
GLYPH_PLAY = "\ue768"
GLYPH_SYNC = "\ue895"
GLYPH_DOCUMENT = "\ue8a5"
GLYPH_RETRY = "\ue72c"
GLYPH_INFO = "\ue946"
GLYPH_WARNING = "\ue7ba"
GLYPH_LOCK = "\ue72e"


def enable_windows_dpi_awareness() -> None:
    """Render crisp text on scaled Windows displays (must run before Tk())."""

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class Fonts:
    title: tkfont.Font
    subtitle: tkfont.Font
    section: tkfont.Font
    label: tkfont.Font
    body: tkfont.Font
    body_bold: tkfont.Font
    small: tkfont.Font
    small_bold: tkfont.Font
    button: tkfont.Font
    button_large: tkfont.Font
    status_title: tkfont.Font
    icon: tkfont.Font | None
    icon_small: tkfont.Font | None
    icon_large: tkfont.Font | None


class Theme:
    """Per-window theme: scale factor, fonts and icon availability."""

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        try:
            dpi = float(root.winfo_fpixels("1i"))
        except tk.TclError:
            dpi = 96.0
        self.scale = max(1.0, dpi / 96.0)
        families = set(tkfont.families(root))
        base = "Segoe UI" if "Segoe UI" in families else "TkDefaultFont"
        semibold = "Segoe UI Semibold" if "Segoe UI Semibold" in families else base
        semibold_weight = "normal" if semibold != base else "bold"
        icon_family = next((f for f in ICON_FONT_CANDIDATES if f in families), None)

        def font(family: str, size: int, weight: str = "normal") -> tkfont.Font:
            return tkfont.Font(root=root, family=family, size=size, weight=weight)

        self.fonts = Fonts(
            title=font(base, 16, "bold"),
            subtitle=font(base, 10),
            section=font(base, 12, "bold"),
            label=font(semibold, 10, semibold_weight),
            body=font(base, 10),
            body_bold=font(base, 10, "bold"),
            small=font(base, 9),
            small_bold=font(base, 9, "bold"),
            button=font(semibold, 10, semibold_weight),
            button_large=font(semibold, 11, semibold_weight),
            status_title=font(base, 11, "bold"),
            icon=font(icon_family, 11) if icon_family else None,
            icon_small=font(icon_family, 9) if icon_family else None,
            icon_large=font(icon_family, 13) if icon_family else None,
        )
        self.has_icons = icon_family is not None

    def px(self, value: float) -> int:
        """Convert a 96-DPI design measure to device pixels."""

        return int(round(value * self.scale))
