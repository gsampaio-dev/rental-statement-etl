"""Reusable Tkinter widgets for the redesigned interface.

Tk has no native rounded corners, so cards, fields and buttons are drawn on
a Canvas using small antialiased corner images plus straight edges. The
widgets keep standard keyboard behavior (Tab focus, Enter/Space to activate).
"""

from __future__ import annotations

from typing import Callable
import tkinter as tk
from tkinter import ttk

from . import theme as t
from .resources import rounded_corner_images
from .theme import Theme


def draw_round_rect(
    canvas: tk.Canvas,
    width: int,
    height: int,
    radius: int,
    fill: str,
    outline: str | None,
    background: str,
    tag: str = "bg",
) -> None:
    canvas.delete(tag)
    if width < 2 or height < 2:
        return
    radius = max(0, min(radius, (min(width, height) - 2) // 2))
    if radius < 2:
        canvas.create_rectangle(
            0, 0, width - 1, height - 1, fill=fill, outline=outline or fill, tags=tag
        )
        canvas.tag_lower(tag)
        return
    r = radius
    tl, tr, bl, br = rounded_corner_images(canvas, r, fill, outline, background)
    canvas.create_rectangle(r, 0, width - r, height, fill=fill, width=0, tags=tag)
    canvas.create_rectangle(0, r, width, height - r, fill=fill, width=0, tags=tag)
    if outline:
        canvas.create_line(r, 0, width - r, 0, fill=outline, tags=tag)
        canvas.create_line(r, height - 1, width - r, height - 1, fill=outline, tags=tag)
        canvas.create_line(0, r, 0, height - r, fill=outline, tags=tag)
        canvas.create_line(width - 1, r, width - 1, height - r, fill=outline, tags=tag)
    canvas.create_image(0, 0, anchor="nw", image=tl, tags=tag)
    canvas.create_image(width, 0, anchor="ne", image=tr, tags=tag)
    canvas.create_image(0, height, anchor="sw", image=bl, tags=tag)
    canvas.create_image(width, height, anchor="se", image=br, tags=tag)
    canvas.tag_lower(tag)


class RoundedPanel(tk.Canvas):
    """A rounded card. Put child widgets inside ``panel.body``.

    By default the panel grows to fit its content; with ``height`` it keeps
    a fixed height and centers the content vertically (used for fields).
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: Theme,
        *,
        fill: str,
        outline: str | None = None,
        background: str | None = None,
        radius: int = 8,
        padding: tuple[int, int] = (16, 16),
        height: int | None = None,
    ) -> None:
        background = background or parent.cget("bg")
        super().__init__(
            parent,
            bg=background,
            highlightthickness=0,
            bd=0,
            width=1,
            height=height or 1,
            takefocus=0,
        )
        self.fill = fill
        self.outline = outline
        self.background = background
        self.radius = theme.px(radius)
        self.padx = theme.px(padding[0])
        self.pady = theme.px(padding[1])
        self.fixed_height = height
        self.body = tk.Frame(self, bg=fill, bd=0, highlightthickness=0)
        anchor = "w" if height else "nw"
        y = (height // 2) if height else self.pady
        self._window = self.create_window(self.padx, y, window=self.body, anchor=anchor)
        self.body.bind("<Configure>", self._on_body_configure, add="+")
        self.bind("<Configure>", self._on_configure, add="+")
        # A 1x1 canvas cannot map its inset body, so Configure alone cannot
        # bootstrap the natural size. Measure once after children are built.
        self.after_idle(self._on_body_configure)

    def _on_body_configure(self, _event: tk.Event | None = None) -> None:
        width = self.body.winfo_reqwidth() + 2 * self.padx
        if int(float(self.cget("width"))) != width:
            self.configure(width=width)
        if not self.fixed_height:
            height = self.body.winfo_reqheight() + 2 * self.pady
            if int(float(self.cget("height"))) != height:
                self.configure(height=height)

    def _on_configure(self, event: tk.Event) -> None:
        self.itemconfigure(self._window, width=max(1, event.width - 2 * self.padx))
        if self.fixed_height:
            self.coords(self._window, self.padx, event.height // 2)
        self._redraw(event.width, event.height)

    def _redraw(self, width: int | None = None, height: int | None = None) -> None:
        width = width or self.winfo_width()
        height = height or self.winfo_height()
        draw_round_rect(
            self, width, height, self.radius, self.fill, self.outline, self.background
        )

    def set_outline(self, outline: str | None) -> None:
        if outline != self.outline:
            self.outline = outline
            self._redraw()


class RoundedButton(tk.Canvas):
    """Flat rounded button with hover, pressed, disabled and focus states."""

    _PALETTES = {
        "primary": {
            "normal": (t.PRIMARY, None, "white", "white"),
            "hover": (t.PRIMARY_HOVER, None, "white", "white"),
            "pressed": (t.PRIMARY_PRESSED, None, "white", "white"),
            "disabled": (t.PRIMARY_DISABLED, None, "#F4F7FC", "#F4F7FC"),
            "focus": "white",
        },
        "secondary": {
            "normal": (t.SURFACE, t.BORDER_STRONG, t.TEXT, t.PRIMARY),
            "hover": (t.SECONDARY_HOVER, t.PRIMARY_TINT_BORDER, t.TEXT, t.PRIMARY),
            "pressed": (t.SECONDARY_PRESSED, t.PRIMARY_TINT_BORDER, t.TEXT, t.PRIMARY),
            "disabled": (t.SURFACE_ALT, t.BORDER, t.TEXT_SUBTLE, t.TEXT_SUBTLE),
            "focus": t.FOCUS,
        },
    }

    def __init__(
        self,
        parent: tk.Misc,
        theme: Theme,
        text: str,
        command: Callable[[], None] | None,
        *,
        variant: str = "primary",
        icon: str | None = None,
        large: bool = False,
        background: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.theme = theme
        self.variant = variant
        self.command = command
        self.text = text
        self.icon = icon if theme.has_icons else None
        self.font = theme.fonts.button_large if large else theme.fonts.button
        self.icon_font = theme.fonts.icon_large if large else theme.fonts.icon
        self.radius = theme.px(8 if large else 6)
        self._hover = False
        self._pressed = False
        self._focused = False
        self.enabled = enabled
        height = theme.px(46 if large else 36)
        super().__init__(
            parent,
            width=self._natural_width(),
            height=height,
            bg=background or parent.cget("bg"),
            highlightthickness=0,
            bd=0,
            takefocus=1 if enabled else 0,
            cursor="hand2" if enabled else "arrow",
        )
        self.bind("<Configure>", lambda _e: self._redraw(), add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<FocusIn>", self._on_focus_in, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Key-space>", lambda _e: self.invoke(), add="+")
        self.bind("<Return>", lambda _e: self.invoke(), add="+")
        self.bind("<KP_Enter>", lambda _e: self.invoke(), add="+")

    # ---- public API -----------------------------------------------------
    def invoke(self) -> None:
        if self.enabled and self.command is not None:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self._pressed = False
        self.configure(takefocus=1 if enabled else 0, cursor="hand2" if enabled else "arrow")
        self._redraw()

    def set_text(self, text: str, icon: str | None = None) -> None:
        self.text = text
        self.icon = icon if self.theme.has_icons else None
        self.configure(width=self._natural_width())
        self._redraw()

    # ---- drawing --------------------------------------------------------
    def _icon_width(self) -> int:
        if not self.icon or self.icon_font is None:
            return 0
        return self.icon_font.measure(self.icon) + self.theme.px(8)

    def _natural_width(self) -> int:
        return self.font.measure(self.text) + self._icon_width() + 2 * self.theme.px(18)

    def _state(self) -> str:
        if not self.enabled:
            return "disabled"
        if self._pressed and self._hover:
            return "pressed"
        if self._hover:
            return "hover"
        return "normal"

    def _redraw(self) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        if width < 4 or height < 4:
            return
        palette = self._PALETTES[self.variant]
        fill, outline, fg, icon_fg = palette[self._state()]
        self.delete("content")
        draw_round_rect(self, width, height, self.radius, fill, outline, self.cget("bg"))
        text_width = self.font.measure(self.text)
        icon_width = self._icon_width()
        x = (width - text_width - icon_width) / 2
        cy = height / 2
        if icon_width and self.icon_font is not None:
            self.create_text(
                x, cy + 1, text=self.icon, font=self.icon_font, fill=icon_fg,
                anchor="w", tags="content",
            )
        self.create_text(
            x + icon_width, cy, text=self.text, font=self.font, fill=fg,
            anchor="w", tags="content",
        )
        if self._focused and self.enabled:
            inset = self.theme.px(3)
            self.create_rectangle(
                inset, inset, width - inset - 1, height - inset - 1,
                outline=palette["focus"], dash=(1, 2), tags="content",
            )

    # ---- events ---------------------------------------------------------
    def _on_enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._redraw()

    def _on_press(self, _event: tk.Event) -> None:
        if not self.enabled:
            return
        self._pressed = True
        self.focus_set()
        self._redraw()

    def _on_release(self, event: tk.Event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._redraw()
        if was_pressed and inside:
            self.invoke()

    def _on_focus_in(self, _event: tk.Event) -> None:
        self._focused = True
        self._redraw()

    def _on_focus_out(self, _event: tk.Event) -> None:
        self._focused = False
        self._redraw()


class ScrollArea(tk.Frame):
    """Vertical scroll container whose scrollbar appears only when needed.

    With ``max_height`` the area shrinks to its content up to that height
    (used for the review list); without it, it fills the space it is given
    (used for the window body so small screens and high DPI stay usable).
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: Theme,
        *,
        background: str,
        max_height: int | None = None,
    ) -> None:
        super().__init__(parent, bg=background, bd=0, highlightthickness=0)
        self.max_height = max_height
        self.canvas = tk.Canvas(
            self,
            bg=background,
            bd=0,
            highlightthickness=0,
            height=1,
            width=1,
            yscrollincrement=theme.px(18),
            takefocus=0,
        )
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview, style="Slim.Vertical.TScrollbar"
        )
        self.inner = tk.Frame(self.canvas, bg=background, bd=0, highlightthickness=0)
        self._window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._scrollbar_visible = False
        self._scrollbar_update_pending = False
        self.canvas._scroll_area = self  # type: ignore[attr-defined]
        self.inner.bind("<Configure>", self._on_inner_configure, add="+")
        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")

    def _on_inner_configure(self, _event: tk.Event | None = None) -> None:
        content_height = self.inner.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, 1, content_height))
        if self.max_height is not None:
            wanted = max(1, min(content_height, self.max_height))
            if int(float(self.canvas.cget("height"))) != wanted:
                self.canvas.configure(height=wanted)
        self._schedule_scrollbar_update()

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._schedule_scrollbar_update()

    def _schedule_scrollbar_update(self) -> None:
        # Wait for grid to map the canvas at its final size. Showing and then
        # hiding the bar during its initial 1px Configure can leave the canvas
        # unmapped on Windows Tk.
        if not self._scrollbar_update_pending:
            self._scrollbar_update_pending = True
            self.after_idle(self._update_scrollbar)

    def _update_scrollbar(self) -> None:
        self._scrollbar_update_pending = False
        needed = self.inner.winfo_reqheight() > self.canvas.winfo_height() + 1
        if needed and not self._scrollbar_visible:
            self.scrollbar.grid(row=0, column=1, sticky="ns")
            self._scrollbar_visible = True
        elif not needed and self._scrollbar_visible:
            self.scrollbar.grid_remove()
            self._scrollbar_visible = False
            self.canvas.yview_moveto(0)

    def can_scroll(self) -> bool:
        return self._scrollbar_visible

    def scroll(self, units: int) -> None:
        if self._scrollbar_visible:
            self.canvas.yview_scroll(units, "units")

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)


def bind_wraplength(label: tk.Label, container: tk.Misc, margin: int, minimum: int) -> None:
    """Wrap a label to its container width (no feedback loop: width-only)."""

    def update(event: tk.Event) -> None:
        wrap = max(minimum, event.width - margin)
        if int(float(label.cget("wraplength") or 0)) != wrap:
            label.configure(wraplength=wrap)

    container.bind("<Configure>", update, add="+")
