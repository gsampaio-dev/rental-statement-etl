"""Tkinter desktop interface for the local rental-statement extractor."""

from __future__ import annotations

import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .app_version import APP_VERSION
from .application_service import (
    count_pdf_files,
    normalize_competence,
    run_application_batch,
)
from .gui_presentation import result_view
from .ui import theme as t
from .ui.resources import BadgeSet, load_product_logo
from .ui.widgets import RoundedButton, RoundedPanel, ScrollArea, bind_wraplength


STATE_READY = "ready"
STATE_PROCESSING = "processing"
STATE_SUCCESS = "success"
STATE_REVIEW = "review"
STATE_ERROR = "error"

TITLE = "Extrator de Demonstrativos de Aluguel"
SUBTITLE = "Exporte os dados dos demonstrativos de aluguel em poucos cliques."
FOLDER_PLACEHOLDER = "Nenhuma pasta selecionada"
COUNT_PLACEHOLDER = "Selecione a pasta dos demonstrativos. As subpastas também são verificadas."


def _work_area(root: tk.Misc) -> tuple[int, int, int, int]:
    """Usable desktop rectangle (excludes the Windows taskbar)."""

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 48


class RentalExtractorWindow:
    def __init__(
        self,
        root: tk.Tk,
        *,
        initial_folder: str | None = None,
        initial_competence: str | None = None,
        automation_run: bool = False,
        automation_close: bool = False,
    ) -> None:
        self.root = root
        self.root.title(f"{TITLE} — v{APP_VERSION}")
        self.theme = t.Theme(root)
        self.badges = BadgeSet(root, self.theme.px)
        try:
            self.root.iconphoto(True, *self.badges.window_icons)
        except tk.TclError:
            pass
        self.root.configure(bg=t.PAGE_BG)

        self.events: queue.Queue[tuple] = queue.Queue()
        self.folder_path: Path | None = None
        self.pdf_count = 0
        self.busy = False
        self.state = STATE_READY
        self.application_run = None
        self.automation_run = automation_run
        self.automation_close = automation_close
        self._processing_started = 0.0
        self._processing_total = 0

        self.folder_var = tk.StringVar(value="")
        self.folder_display_var = tk.StringVar(value=FOLDER_PLACEHOLDER)
        self.pdf_count_var = tk.StringVar(value=COUNT_PLACEHOLDER)
        self.period_var = tk.StringVar(value="")
        self.period_error_var = tk.StringVar(value="")
        self.elapsed_var = tk.StringVar(value="")

        self.generate_button: RoundedButton | None = None
        self.open_folder_button: RoundedButton | None = None
        self.diagnostics_button: RoundedButton | None = None
        self.new_report_button: RoundedButton | None = None
        self.retry_button: RoundedButton | None = None
        self.progress: ttk.Progressbar | None = None

        self._place_window()
        self._configure_ttk_styles()
        self._build_widgets()
        self._show_ready()
        self.period_var.trace_add("write", self._on_period_changed)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.root.after(100, self._poll_events)
        if initial_competence:
            self.period_var.set(initial_competence)
        if initial_folder:
            self.root.after(0, lambda: self._count_selected_folder(initial_folder))

    # ------------------------------------------------------------------
    # Window and layout
    # ------------------------------------------------------------------
    def _place_window(self) -> None:
        px = self.theme.px
        left, top, area_w, area_h = _work_area(self.root)
        title_bar = px(32)
        width = min(px(780), area_w - px(16))
        height = min(px(740), area_h - title_bar - px(8))
        self.list_visible_rows = 3 if area_h >= px(820) else 2
        x = left + max(0, (area_w - width) // 2)
        y = top + max(0, (area_h - height - title_bar) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(px(620), width), min(px(500), height))

    def _configure_ttk_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        px = self.theme.px
        style.configure(
            "Activity.Horizontal.TProgressbar",
            troughcolor="#DCE6F4",
            background=t.PRIMARY,
            bordercolor="#DCE6F4",
            lightcolor=t.PRIMARY,
            darkcolor=t.PRIMARY,
            thickness=px(6),
        )
        style.configure(
            "Slim.Vertical.TScrollbar",
            gripcount=0,
            background="#C9D3E0",
            troughcolor=t.PAGE_BG,
            bordercolor=t.PAGE_BG,
            lightcolor="#C9D3E0",
            darkcolor="#C9D3E0",
            arrowcolor=t.TEXT_MUTED,
            arrowsize=px(12),
        )
        style.map("Slim.Vertical.TScrollbar", background=[("active", "#AEBBCC")])

    def _build_widgets(self) -> None:
        px = self.theme.px
        fonts = self.theme.fonts
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # Header: application identity on the left, project badge on the right.
        header = tk.Frame(root, bg=t.SURFACE)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        titles = tk.Frame(header, bg=t.SURFACE)
        titles.grid(row=0, column=0, sticky="ew", padx=(px(24), px(16)), pady=px(14))
        self.title_label = tk.Label(
            titles, text=TITLE, font=fonts.title, fg=t.TEXT, bg=t.SURFACE,
            anchor="w", justify="left",
        )
        self.title_label.pack(anchor="w", fill="x")
        self.subtitle_label = tk.Label(
            titles, text=SUBTITLE, font=fonts.subtitle, fg=t.TEXT_MUTED, bg=t.SURFACE,
            anchor="w", justify="left",
        )
        self.subtitle_label.pack(anchor="w", fill="x", pady=(px(2), 0))
        bind_wraplength(self.title_label, titles, 0, px(200))
        bind_wraplength(self.subtitle_label, titles, 0, px(200))

        self.logo_image = load_product_logo(root, px(72))
        self.logo_label: tk.Label | None = None
        if self.logo_image is not None:
            tk.Frame(header, bg=t.BORDER, width=1).grid(
                row=0, column=1, sticky="ns", pady=px(18)
            )
            self.logo_label = tk.Label(
                header,
                image=self.logo_image,
                bg=t.SURFACE,
                bd=0,
                highlightthickness=0,
            )
            self.logo_label.grid(row=0, column=2, sticky="e", padx=(px(18), px(22)), pady=px(6))
        tk.Frame(root, bg=t.BORDER, height=1).grid(row=1, column=0, sticky="ew")

        # Scrollable body (only scrolls on very small screens / high DPI).
        self.page = ScrollArea(root, self.theme, background=t.PAGE_BG)
        self.page.grid(row=2, column=0, sticky="nsew")
        self.card = RoundedPanel(
            self.page.inner,
            self.theme,
            fill=t.SURFACE,
            outline=t.BORDER,
            background=t.PAGE_BG,
            radius=10,
            padding=(22, 18),
        )
        self.card.pack(fill="x", padx=px(18), pady=(px(14), px(12)))
        body = self.card.body
        body.columnconfigure(0, weight=1)

        # Section header
        section = tk.Frame(body, bg=t.SURFACE)
        section.grid(row=0, column=0, sticky="ew", pady=(0, px(14)))
        section.columnconfigure(1, weight=1)
        tk.Label(section, image=self.badges.section, bg=t.SURFACE, bd=0).grid(
            row=0, column=0, rowspan=2, sticky="nw", padx=(0, px(12))
        )
        tk.Label(
            section,
            text="Gerar relatório de aluguéis",
            font=fonts.section,
            fg=t.TEXT,
            bg=t.SURFACE,
        ).grid(row=0, column=1, sticky="w")
        section_help = tk.Label(
            section,
            text=(
                "Selecione a pasta com os demonstrativos em PDF e, se desejar, "
                "informe a competência do relatório."
            ),
            font=fonts.small,
            fg=t.TEXT_MUTED,
            bg=t.SURFACE,
            justify="left",
            anchor="w",
        )
        section_help.grid(row=1, column=1, sticky="w")
        bind_wraplength(section_help, section, px(60), px(240))

        # Folder
        tk.Label(
            body, text="Pasta dos demonstrativos", font=fonts.label, fg=t.TEXT, bg=t.SURFACE
        ).grid(row=1, column=0, sticky="w", pady=(0, px(4)))
        folder_row = tk.Frame(body, bg=t.SURFACE)
        folder_row.grid(row=2, column=0, sticky="ew")
        folder_row.columnconfigure(0, weight=1)
        self.folder_field = RoundedPanel(
            folder_row,
            self.theme,
            fill=t.SURFACE,
            outline=t.BORDER_STRONG,
            background=t.SURFACE,
            radius=6,
            padding=(10, 0),
            height=px(36),
        )
        self.folder_field.grid(row=0, column=0, sticky="ew", padx=(0, px(10)))
        field = self.folder_field.body
        field.columnconfigure(1, weight=1)
        if self.theme.has_icons:
            tk.Label(
                field, text=t.GLYPH_FOLDER, font=fonts.icon, fg="#D99A1E", bg=t.SURFACE
            ).grid(row=0, column=0, padx=(0, px(8)))
        self.folder_entry = tk.Entry(
            field,
            textvariable=self.folder_display_var,
            state="readonly",
            readonlybackground=t.SURFACE,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=fonts.body,
            fg=t.TEXT_SUBTLE,
            takefocus=0,
            cursor="arrow",
        )
        self.folder_entry.grid(row=0, column=1, sticky="ew")
        self.select_button = RoundedButton(
            folder_row,
            self.theme,
            "Selecionar pasta",
            self._select_folder,
            variant="secondary",
            icon=t.GLYPH_FOLDER_OPEN,
            background=t.SURFACE,
        )
        self.select_button.grid(row=0, column=1, sticky="e")

        count_row = tk.Frame(body, bg=t.SURFACE)
        count_row.grid(row=3, column=0, sticky="ew", pady=(px(7), px(12)))
        self.count_badge = tk.Label(count_row, image=self.badges.pdf, bg=t.SURFACE, bd=0)
        self.count_label = tk.Label(
            count_row,
            textvariable=self.pdf_count_var,
            font=fonts.body,
            fg=t.TEXT_MUTED,
            bg=t.SURFACE,
            anchor="w",
            justify="left",
        )
        self.count_label.grid(row=0, column=1, sticky="w")
        bind_wraplength(self.count_label, count_row, px(40), px(240))

        # Competence
        tk.Label(
            body, text="Competência (opcional)", font=fonts.label, fg=t.TEXT, bg=t.SURFACE
        ).grid(row=4, column=0, sticky="w", pady=(0, px(4)))
        period_row = tk.Frame(body, bg=t.SURFACE)
        period_row.grid(row=5, column=0, sticky="ew")
        self.period_field = RoundedPanel(
            period_row,
            self.theme,
            fill=t.SURFACE,
            outline=t.BORDER_STRONG,
            background=t.SURFACE,
            radius=6,
            padding=(10, 0),
            height=px(36),
        )
        self.period_field.grid(row=0, column=0, sticky="w")
        pfield = self.period_field.body
        if self.theme.has_icons:
            tk.Label(
                pfield, text=t.GLYPH_CALENDAR, font=fonts.icon, fg=t.TEXT_MUTED, bg=t.SURFACE
            ).grid(row=0, column=0, padx=(0, px(8)))
        validate = (self.root.register(self._validate_period_keystroke), "%P")
        self.period_entry = tk.Entry(
            pfield,
            textvariable=self.period_var,
            width=10,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=fonts.body,
            fg=t.TEXT,
            bg=t.SURFACE,
            disabledbackground=t.SURFACE,
            disabledforeground=t.TEXT_SUBTLE,
            insertbackground=t.TEXT,
            validate="key",
            validatecommand=validate,
        )
        self.period_entry.grid(row=0, column=1, sticky="w")
        self.period_entry.bind("<FocusIn>", lambda _e: self.period_field.set_outline(t.FOCUS))
        self.period_entry.bind(
            "<FocusOut>", lambda _e: self._refresh_period_outline(), add="+"
        )
        self.period_entry.bind("<Return>", lambda _e: self._start_processing())
        self.period_entry.bind("<KP_Enter>", lambda _e: self._start_processing())
        tk.Label(
            period_row,
            text="MM/AAAA  ·  ex.: 09/2026",
            font=fonts.small,
            fg=t.TEXT_SUBTLE,
            bg=t.SURFACE,
        ).grid(row=0, column=1, sticky="w", padx=(px(12), 0))

        self.period_error = tk.Frame(body, bg=t.SURFACE)
        self.period_error.grid(row=6, column=0, sticky="w", pady=(px(6), 0))
        if self.theme.has_icons:
            tk.Label(
                self.period_error,
                text=t.GLYPH_WARNING,
                font=fonts.icon_small,
                fg=t.DANGER,
                bg=t.SURFACE,
            ).grid(row=0, column=0, padx=(0, px(6)))
        tk.Label(
            self.period_error,
            textvariable=self.period_error_var,
            font=fonts.small,
            fg=t.DANGER_TEXT,
            bg=t.SURFACE,
        ).grid(row=0, column=1, sticky="w")
        self.period_error.grid_remove()

        # Dynamic area: generate button / progress / result.
        self.action_area = tk.Frame(body, bg=t.SURFACE)
        self.action_area.grid(row=7, column=0, sticky="ew", pady=(px(16), 0))
        self.action_area.columnconfigure(0, weight=1)

        # Footer
        footer = tk.Frame(root, bg=t.PAGE_BG)
        footer.grid(row=3, column=0, sticky="ew", padx=px(22), pady=(0, px(8)))
        footer.columnconfigure(1, weight=1)
        if self.theme.has_icons:
            tk.Label(
                footer, text=t.GLYPH_INFO, font=fonts.icon_small, fg=t.TEXT_SUBTLE, bg=t.PAGE_BG
            ).grid(row=0, column=0, padx=(0, px(6)))
        footer_text = tk.Label(
            footer,
            text=(
                "PDFs com dados ausentes ou ambíguos ficam fora do Excel e aparecem para revisão."
            ),
            font=fonts.small,
            fg=t.TEXT_MUTED,
            bg=t.PAGE_BG,
            anchor="w",
            justify="left",
        )
        footer_text.grid(row=0, column=1, sticky="w")
        bind_wraplength(footer_text, footer, px(110), px(200))
        tk.Label(
            footer, text=f"Versão {APP_VERSION}", font=fonts.small, fg=t.TEXT_SUBTLE, bg=t.PAGE_BG
        ).grid(row=0, column=2, sticky="e", padx=(px(12), 0))

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _clear_action_area(self) -> None:
        if self.progress is not None:
            try:
                self.progress.stop()
            except tk.TclError:
                pass
        for child in self.action_area.winfo_children():
            child.destroy()
        self.generate_button = None
        self.open_folder_button = None
        self.diagnostics_button = None
        self.new_report_button = None
        self.retry_button = None
        self.progress = None

    def _set_count_text(self, text: str, *, tone: str = "muted", badge: bool = False) -> None:
        colors = {
            "muted": t.TEXT_MUTED,
            "normal": t.TEXT,
            "warning": t.WARNING_TEXT,
            "danger": t.DANGER_TEXT,
        }
        self.pdf_count_var.set(text)
        self.count_label.configure(fg=colors[tone])
        if badge:
            self.count_badge.grid(row=0, column=0, sticky="w", padx=(0, self.theme.px(8)))
        else:
            self.count_badge.grid_remove()

    def _set_folder_display(self, folder: str | Path | None) -> None:
        if folder:
            self.folder_var.set(str(folder))
            self.folder_display_var.set(str(folder))
            self.folder_entry.configure(fg=t.TEXT)
            self.folder_entry.xview_moveto(1.0)
        else:
            self.folder_var.set("")
            self.folder_display_var.set(FOLDER_PLACEHOLDER)
            self.folder_entry.configure(fg=t.TEXT_SUBTLE)

    def _show_period_error(self, message: str | None) -> None:
        if message:
            self.period_error_var.set(message)
            self.period_error.grid()
        else:
            self.period_error_var.set("")
            self.period_error.grid_remove()
        self._refresh_period_outline()

    def _refresh_period_outline(self) -> None:
        if self.period_error_var.get():
            self.period_field.set_outline(t.DANGER)
        elif self.root.focus_get() is self.period_entry:
            self.period_field.set_outline(t.FOCUS)
        else:
            self.period_field.set_outline(t.BORDER_STRONG)

    @staticmethod
    def _validate_period_keystroke(proposed: str) -> bool:
        return len(proposed) <= 7 and all(ch.isdigit() or ch == "/" for ch in proposed)

    def _on_period_changed(self, *_args: object) -> None:
        if self.period_error_var.get():
            self._show_period_error(None)
        if self.state in (STATE_SUCCESS, STATE_REVIEW, STATE_ERROR) and not self.busy:
            self._show_ready()

    def _on_mousewheel(self, event: tk.Event) -> None:
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        steps = -1 if event.delta > 0 else 1
        steps *= max(1, abs(int(event.delta)) // 120)
        while widget is not None:
            area = getattr(widget, "_scroll_area", None)
            if area is not None and area.can_scroll():
                area.scroll(steps)
                return
            widget = getattr(widget, "master", None)

    def _status_panel(
        self, parent: tk.Misc, *, fill: str, outline: str
    ) -> RoundedPanel:
        return RoundedPanel(
            parent,
            self.theme,
            fill=fill,
            outline=outline,
            background=t.SURFACE,
            radius=8,
            padding=(16, 12),
        )

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------
    def _show_ready(self) -> None:
        px = self.theme.px
        self.state = STATE_READY
        self.application_run = None
        self._clear_action_area()
        area = self.action_area
        self.generate_button = RoundedButton(
            area,
            self.theme,
            "Gerar relatório",
            self._start_processing,
            variant="primary",
            icon=t.GLYPH_PLAY,
            large=True,
            background=t.SURFACE,
        )
        self.generate_button.grid(row=0, column=0, sticky="ew")
        hint = tk.Frame(area, bg=t.SURFACE)
        hint.grid(row=1, column=0, pady=(px(10), 0))
        tk.Label(hint, image=self.badges.excel, bg=t.SURFACE, bd=0).grid(
            row=0, column=0, padx=(0, px(8))
        )
        tk.Label(
            hint,
            text="O relatório será salvo em Excel (.xlsx)",
            font=self.theme.fonts.small,
            fg=t.TEXT_MUTED,
            bg=t.SURFACE,
        ).grid(row=0, column=1)
        self._set_controls_busy(self.busy)

    def _show_processing(self) -> None:
        px = self.theme.px
        fonts = self.theme.fonts
        self.state = STATE_PROCESSING
        self._clear_action_area()
        area = self.action_area
        self.generate_button = RoundedButton(
            area,
            self.theme,
            "Processando…",
            None,
            variant="primary",
            large=True,
            background=t.SURFACE,
            enabled=False,
        )
        self.generate_button.grid(row=0, column=0, sticky="ew")
        panel = self._status_panel(area, fill=t.PRIMARY_TINT, outline=t.PRIMARY_TINT_BORDER)
        panel.grid(row=1, column=0, sticky="ew", pady=(px(12), 0))
        pb = panel.body
        pb.columnconfigure(0, weight=1)
        total = self._processing_total
        tk.Label(
            pb,
            text=f"Processando {total} PDF{'s' if total != 1 else ''}…",
            font=fonts.body_bold,
            fg=t.TEXT,
            bg=t.PRIMARY_TINT,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            pb, textvariable=self.elapsed_var, font=fonts.small, fg=t.TEXT_MUTED, bg=t.PRIMARY_TINT
        ).grid(row=0, column=1, sticky="e")
        self.progress = ttk.Progressbar(
            pb, mode="indeterminate", style="Activity.Horizontal.TProgressbar"
        )
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(px(8), px(8)))
        self.progress.start(18)
        note = tk.Label(
            pb,
            text=(
                "A janela continua disponível durante o processamento. "
                "PDFs digitalizados passam por OCR e podem levar mais tempo."
            ),
            font=fonts.small,
            fg=t.TEXT_MUTED,
            bg=t.PRIMARY_TINT,
            justify="left",
            anchor="w",
        )
        note.grid(row=2, column=0, columnspan=2, sticky="w")
        bind_wraplength(note, pb, px(8), px(220))
        self._tick_elapsed()

    def _tick_elapsed(self) -> None:
        if self.state != STATE_PROCESSING:
            return
        seconds = int(time.monotonic() - self._processing_started)
        self.elapsed_var.set(f"Tempo decorrido: {seconds // 60}:{seconds % 60:02d}")
        self.root.after(1000, self._tick_elapsed)

    def _show_result(self, application_run) -> None:
        px = self.theme.px
        fonts = self.theme.fonts
        report = application_run.report
        view = result_view(report)
        self.application_run = application_run
        self.state = STATE_REVIEW if view.needs_review else STATE_SUCCESS
        self._clear_action_area()
        area = self.action_area
        if view.needs_review:
            fill, outline, title_fg, badge = (
                t.WARNING_BG, t.WARNING_BORDER, t.WARNING_TEXT, self.badges.warning,
            )
        else:
            fill, outline, title_fg, badge = (
                t.SUCCESS_BG, t.SUCCESS_BORDER, t.SUCCESS_TEXT, self.badges.success,
            )

        # Status summary
        panel = self._status_panel(area, fill=fill, outline=outline)
        panel.grid(row=0, column=0, sticky="ew")
        pb = panel.body
        pb.columnconfigure(1, weight=1)
        tk.Label(pb, image=badge, bg=fill, bd=0).grid(
            row=0, column=0, rowspan=2, sticky="nw", padx=(0, px(14)), pady=(px(2), 0)
        )
        self.status_title = tk.Label(
            pb, text=view.title, font=fonts.status_title, fg=title_fg, bg=fill,
            anchor="w", justify="left",
        )
        self.status_title.grid(row=0, column=1, sticky="w")
        bind_wraplength(self.status_title, pb, px(60), px(200))
        metrics = tk.Frame(pb, bg=fill)
        metrics.grid(row=1, column=1, sticky="ew", pady=(px(6), 0))
        metrics.columnconfigure((0, 1), weight=1, uniform="metric")
        self.metric_labels: list[str] = []
        for index, (number, label) in enumerate(view.metrics):
            cell = tk.Frame(metrics, bg=fill)
            cell.grid(row=index // 2, column=index % 2, sticky="ew", pady=(0, px(2)))
            cell.columnconfigure(1, weight=1)
            number_label = tk.Label(cell, text=number, font=fonts.body_bold, fg=t.TEXT, bg=fill)
            number_label.grid(row=0, column=0, sticky="nw")
            metric_label = tk.Label(
                cell, text=f" {label}", font=fonts.body, fg=t.TEXT, bg=fill,
                anchor="w", justify="left",
            )
            metric_label.grid(row=0, column=1, sticky="w")
            bind_wraplength(metric_label, cell, number_label.winfo_reqwidth() + px(8), px(100))
            self.metric_labels.append(f"{number} {label}")

        row = 1
        # Review list and warnings
        if view.review_items or view.warning_items:
            if view.review_items:
                heading = f"Documentos que requerem revisão ({len(view.review_items)})"
            else:
                heading = f"Avisos ({len(view.warning_items)})"
            tk.Label(area, text=heading, font=fonts.label, fg=t.TEXT, bg=t.SURFACE).grid(
                row=row, column=0, sticky="w", pady=(px(12), px(6))
            )
            row += 1
            row_height = px(52)
            self.review_list = ScrollArea(
                area,
                self.theme,
                background=t.SURFACE,
                max_height=row_height * self.list_visible_rows,
            )
            self.review_list.grid(row=row, column=0, sticky="ew")
            row += 1
            items = self.review_list.inner
            items.columnconfigure(0, weight=1)
            item_row = 0
            for file_name, reason in view.review_items:
                self._list_item(items, item_row, file_name, reason, tone="review")
                item_row += 1
            if view.review_items and view.warning_items:
                tk.Label(
                    items,
                    text=f"Avisos ({len(view.warning_items)})",
                    font=fonts.small_bold,
                    fg=t.TEXT_MUTED,
                    bg=t.SURFACE,
                ).grid(row=item_row, column=0, sticky="w", pady=(px(4), px(4)))
                item_row += 1
            for file_name, reason in view.warning_items:
                self._list_item(items, item_row, file_name, reason, tone="warning")
                item_row += 1

        # Generated workbook
        file_card = RoundedPanel(
            area,
            self.theme,
            fill=t.SURFACE_ALT,
            outline=t.BORDER,
            background=t.SURFACE,
            radius=8,
            padding=(14, 10),
        )
        file_card.grid(row=row, column=0, sticky="ew", pady=(px(12), 0))
        row += 1
        fb = file_card.body
        fb.columnconfigure(1, weight=1)
        tk.Label(fb, image=self.badges.excel_large, bg=t.SURFACE_ALT, bd=0).grid(
            row=0, column=0, rowspan=2, padx=(0, px(12))
        )
        caption = (
            "Relatório gerado com os documentos validados"
            if view.needs_review
            else "Relatório gerado com sucesso!"
        )
        tk.Label(
            fb, text=caption, font=fonts.small, fg=t.TEXT_MUTED, bg=t.SURFACE_ALT, anchor="w"
        ).grid(row=0, column=1, sticky="w")
        self.output_label = tk.Label(
            fb,
            text=view.output_name,
            font=fonts.body_bold,
            fg=t.TEXT,
            bg=t.SURFACE_ALT,
            anchor="w",
        )
        self.output_label.grid(row=1, column=1, sticky="w")
        bind_wraplength(self.output_label, fb, px(56), px(160))

        if application_run.log_error:
            note = tk.Label(
                area,
                text=(
                    "A planilha foi gerada, mas o log legível não pôde ser salvo. "
                    "Os diagnósticos JSON foram preservados."
                ),
                font=fonts.small,
                fg=t.WARNING_TEXT,
                bg=t.SURFACE,
                justify="left",
                anchor="w",
            )
            note.grid(row=row, column=0, sticky="w", pady=(px(8), 0))
            bind_wraplength(note, area, px(8), px(220))
            row += 1

        # Actions
        actions = tk.Frame(area, bg=t.SURFACE)
        actions.grid(row=row, column=0, sticky="ew", pady=(px(14), 0))
        actions.columnconfigure((0, 1, 2), weight=1, uniform="actions")
        self.open_folder_button = RoundedButton(
            actions,
            self.theme,
            "Abrir pasta",
            self._open_output_folder,
            variant="secondary",
            icon=t.GLYPH_FOLDER_OPEN,
            background=t.SURFACE,
        )
        self.open_folder_button.grid(row=0, column=0, sticky="ew", padx=(0, px(8)))
        self.diagnostics_button = RoundedButton(
            actions,
            self.theme,
            "Ver diagnóstico",
            self._open_diagnostics,
            variant="secondary",
            icon=t.GLYPH_DOCUMENT,
            background=t.SURFACE,
        )
        self.diagnostics_button.grid(row=0, column=1, sticky="ew", padx=(0, px(8)))
        self.new_report_button = RoundedButton(
            actions,
            self.theme,
            "Gerar novo relatório",
            self._new_report,
            variant="primary",
            icon=t.GLYPH_SYNC,
            background=t.SURFACE,
        )
        self.new_report_button.grid(row=0, column=2, sticky="ew")
        self._adapt_result_actions(actions)

        if self.automation_close:
            self.root.after(1000, self.root.destroy)

    def _adapt_result_actions(self, actions: tk.Frame) -> None:
        """Keep the existing action buttons legible in narrow/scaled windows."""

        buttons = (self.open_folder_button, self.diagnostics_button, self.new_report_button)
        gap = self.theme.px(8)
        required = max(button.winfo_reqwidth() for button in buttons) * 3 + gap * 2
        last_stacked = None

        def layout(event: tk.Event) -> None:
            nonlocal last_stacked
            stacked = event.width < required
            if stacked == last_stacked:
                return
            last_stacked = stacked
            for column in range(3):
                actions.columnconfigure(column, weight=1 if column == 0 or not stacked else 0)
            for index, button in enumerate(buttons):
                button.grid_configure(
                    row=index if stacked else 0,
                    column=0 if stacked else index,
                    columnspan=3 if stacked else 1,
                    padx=0 if stacked or index == 2 else (0, gap),
                    pady=(0, gap if stacked and index < 2 else 0),
                )

        actions.bind("<Configure>", layout, add="+")

    def _list_item(
        self, parent: tk.Misc, row: int, file_name: str, reason: str, *, tone: str
    ) -> None:
        px = self.theme.px
        fonts = self.theme.fonts
        item = tk.Frame(
            parent,
            bg=t.SURFACE_ALT,
            highlightthickness=1,
            highlightbackground=t.BORDER,
            highlightcolor=t.BORDER,
        )
        item.grid(row=row, column=0, sticky="ew", pady=(0, px(6)))
        item.columnconfigure(1, weight=1)
        tk.Label(item, image=self.badges.pdf_large, bg=t.SURFACE_ALT, bd=0).grid(
            row=0, column=0, rowspan=2, padx=(px(10), px(10)), pady=px(6)
        )
        name = tk.Label(
            item,
            text=file_name,
            font=fonts.body_bold,
            fg=t.TEXT,
            bg=t.SURFACE_ALT,
            anchor="w",
            justify="left",
        )
        name.grid(row=0, column=1, sticky="w", pady=(px(6), 0), padx=(0, px(10)))
        detail = tk.Label(
            item,
            text=reason,
            font=fonts.small,
            fg=t.WARNING_TEXT if tone == "review" else t.TEXT_MUTED,
            bg=t.SURFACE_ALT,
            anchor="w",
            justify="left",
        )
        detail.grid(row=1, column=1, sticky="w", pady=(0, px(6)), padx=(0, px(10)))
        bind_wraplength(name, item, px(70), px(160))
        bind_wraplength(detail, item, px(70), px(160))

    def _show_error(self) -> None:
        px = self.theme.px
        fonts = self.theme.fonts
        self.state = STATE_ERROR
        self._clear_action_area()
        area = self.action_area
        panel = self._status_panel(area, fill=t.DANGER_BG, outline=t.DANGER_BORDER)
        panel.grid(row=0, column=0, sticky="ew")
        pb = panel.body
        pb.columnconfigure(1, weight=1)
        tk.Label(pb, image=self.badges.error, bg=t.DANGER_BG, bd=0).grid(
            row=0, column=0, rowspan=2, sticky="nw", padx=(0, px(14))
        )
        tk.Label(
            pb,
            text="Não foi possível gerar o relatório",
            font=fonts.status_title,
            fg=t.DANGER_TEXT,
            bg=t.DANGER_BG,
        ).grid(row=0, column=1, sticky="w")
        message = tk.Label(
            pb,
            text="Verifique se a pasta permite gravação e tente novamente.",
            font=fonts.body,
            fg=t.TEXT,
            bg=t.DANGER_BG,
            justify="left",
            anchor="w",
        )
        message.grid(row=1, column=1, sticky="w", pady=(px(4), 0))
        bind_wraplength(message, pb, px(70), px(200))
        actions = tk.Frame(area, bg=t.SURFACE)
        actions.grid(row=1, column=0, sticky="ew", pady=(px(14), 0))
        actions.columnconfigure((0, 1), weight=1, uniform="actions")
        self.new_report_button = RoundedButton(
            actions,
            self.theme,
            "Gerar novo relatório",
            self._new_report,
            variant="secondary",
            icon=t.GLYPH_SYNC,
            background=t.SURFACE,
        )
        self.new_report_button.grid(row=0, column=0, sticky="ew", padx=(0, px(8)))
        self.retry_button = RoundedButton(
            actions,
            self.theme,
            "Tentar novamente",
            self._start_processing,
            variant="primary",
            icon=t.GLYPH_RETRY,
            background=t.SURFACE,
        )
        self.retry_button.grid(row=0, column=1, sticky="ew")

    # ------------------------------------------------------------------
    # Behavior (same workflow and service calls as before the redesign)
    # ------------------------------------------------------------------
    def _set_controls_busy(self, busy: bool) -> None:
        self.busy = busy
        self.select_button.set_enabled(not busy)
        self.period_entry.configure(state="disabled" if busy else "normal")
        can_generate = not busy and self.folder_path is not None and self.pdf_count > 0
        if self.generate_button is not None and self.state == STATE_READY:
            self.generate_button.set_enabled(can_generate)
        if self.retry_button is not None:
            self.retry_button.set_enabled(can_generate)

    def _select_folder(self) -> None:
        if self.busy:
            return
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Selecione a pasta dos demonstrativos em PDF",
            mustexist=True,
        )
        if not selected:
            return
        self._count_selected_folder(selected)

    def _count_selected_folder(self, selected: str | Path) -> None:
        self.folder_path = Path(selected)
        self._set_folder_display(selected)
        self.pdf_count = 0
        if self.state != STATE_READY:
            self._show_ready()
        self._set_count_text("Contando PDFs na pasta e nas subpastas…")
        self._set_controls_busy(True)
        threading.Thread(
            target=self._count_worker,
            args=(self.folder_path,),
            name="pdf-count",
            daemon=True,
        ).start()

    def _count_worker(self, folder: Path) -> None:
        try:
            self.events.put(("count", folder, count_pdf_files(folder), None))
        except Exception as exc:
            self.events.put(("count", folder, None, exc))

    def _start_processing(self) -> None:
        if self.busy or self.folder_path is None:
            return
        try:
            normalize_competence(self.period_var.get())
        except ValueError as exc:
            self._show_period_error(str(exc))
            self.period_entry.focus_set()
            return
        if self.pdf_count == 0:
            messagebox.showinfo(
                "Nenhum PDF encontrado",
                "Selecione uma pasta que contenha demonstrativos em PDF.",
                parent=self.root,
            )
            return

        folder = self.folder_path
        competence = self.period_var.get()
        self._show_period_error(None)
        self._processing_total = self.pdf_count
        self._processing_started = time.monotonic()
        self._set_controls_busy(True)
        self._show_processing()
        threading.Thread(
            target=self._batch_worker,
            args=(folder, competence),
            name="rental-batch",
            daemon=True,
        ).start()

    def _batch_worker(self, folder: Path, competence: str) -> None:
        try:
            self.events.put(("batch", run_application_batch(folder, competence), None))
        except Exception as exc:
            self.events.put(("batch", None, exc))

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "count":
                    _, folder, count, error = event
                    if folder != self.folder_path:
                        continue
                    if error is not None:
                        self._set_controls_busy(False)
                        self._set_count_text(
                            "Não foi possível ler esta pasta. Selecione uma pasta válida.",
                            tone="danger",
                        )
                        messagebox.showerror(
                            "Pasta indisponível",
                            "Não foi possível contar os PDFs nesta pasta.",
                            parent=self.root,
                        )
                    else:
                        self.pdf_count = count
                        if count:
                            self._set_count_text(
                                f"{count} PDF{'s' if count != 1 else ''} "
                                f"encontrado{'s' if count != 1 else ''}",
                                tone="normal",
                                badge=True,
                            )
                        else:
                            self._set_count_text(
                                "Nenhum PDF encontrado nesta pasta ou nas subpastas.",
                                tone="warning",
                            )
                        self._set_controls_busy(False)
                        if self.automation_run and count:
                            self.automation_run = False
                            self.root.after(0, self._start_processing)
                elif event[0] == "batch":
                    _, application_run, error = event
                    self._set_controls_busy(False)
                    if error is not None:
                        self._show_error()
                        self._set_controls_busy(False)
                        messagebox.showerror(
                            "Falha ao gerar relatório",
                            "O relatório não foi concluído. Verifique se a pasta permite gravação e tente novamente.",
                            parent=self.root,
                        )
                        continue
                    self._show_result(application_run)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _new_report(self) -> None:
        """Start over, exactly like reopening the application."""

        if self.busy:
            return
        self.folder_path = None
        self.pdf_count = 0
        self._set_folder_display(None)
        self._set_count_text(COUNT_PLACEHOLDER)
        self.period_var.set("")
        self._show_period_error(None)
        self._show_ready()
        self.page.scroll_to_top()
        self.select_button.focus_set()

    def _open_output_folder(self) -> None:
        if self.folder_path is None:
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(self.folder_path))
            else:
                raise OSError("A abertura de pastas está disponível na versão Windows.")
        except OSError:
            messagebox.showerror(
                "Não foi possível abrir a pasta",
                "Abra manualmente a pasta selecionada para localizar o Excel.",
                parent=self.root,
            )

    def _diagnostics_target(self) -> Path | None:
        run = self.application_run
        if run is None:
            return None
        if run.log_path is not None and Path(run.log_path).is_file():
            return Path(run.log_path)
        diagnostics = run.report.diagnostics_path
        if diagnostics is not None and Path(diagnostics).is_file():
            return Path(diagnostics)
        return None

    def _open_diagnostics(self) -> None:
        target = self._diagnostics_target()
        try:
            if target is None:
                raise OSError("diagnóstico indisponível")
            if hasattr(os, "startfile"):
                os.startfile(str(target))
            else:
                raise OSError("A abertura de arquivos está disponível na versão Windows.")
        except OSError:
            messagebox.showerror(
                "Não foi possível abrir o diagnóstico",
                "Abra manualmente o arquivo .execution.log salvo ao lado do Excel.",
                parent=self.root,
            )


def main(
    *,
    initial_folder: str | None = None,
    initial_competence: str | None = None,
    automation_run: bool = False,
    automation_close: bool = False,
) -> None:
    t.enable_windows_dpi_awareness()
    root = tk.Tk()
    RentalExtractorWindow(
        root,
        initial_folder=initial_folder,
        initial_competence=initial_competence,
        automation_run=automation_run,
        automation_close=automation_close,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
