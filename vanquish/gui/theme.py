"""Colours and ttk styling. Uses the cross-platform 'clam' engine so it looks the same everywhere."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

PALETTES = {
    "dark": {
        "bg": "#1e1f22", "surface": "#2b2d31", "surface2": "#35373c", "fg": "#e8e8e8",
        "muted": "#9ba1a6", "accent": "#3fa34d", "accent_hover": "#4dbb5c", "accent_fg": "#ffffff",
        "select": "#3b5b86", "select_fg": "#ffffff", "border": "#40434a", "danger": "#e05252",
        "warn": "#e0a84f", "entry": "#232428", "tile": "#2b2d31", "tile_hover": "#34363c",
    },
    "light": {
        "bg": "#f2f3f5", "surface": "#ffffff", "surface2": "#e6e7ea", "fg": "#1d1e21",
        "muted": "#5f6368", "accent": "#2f8f3c", "accent_hover": "#37a546", "accent_fg": "#ffffff",
        "select": "#cde1fb", "select_fg": "#0b1f3a", "border": "#c9ccd1", "danger": "#c62828",
        "warn": "#a86b00", "entry": "#ffffff", "tile": "#ffffff", "tile_hover": "#eef0f3",
    },
}


class Theme:
    def __init__(self, root: tk.Tk, name: str = "dark"):
        self.root = root
        self.name = name if name in PALETTES else "dark"
        self.c = dict(PALETTES[self.name])
        self.fonts = {}
        self.apply()

    def _setup_fonts(self):
        default = tkfont.nametofont("TkDefaultFont")
        size = max(abs(int(default.cget("size"))), 10)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(size=size)
            except tk.TclError:
                pass
        family = default.cget("family")
        self.fonts = {
            "normal": tkfont.Font(family=family, size=size),
            "bold": tkfont.Font(family=family, size=size, weight="bold"),
            "small": tkfont.Font(family=family, size=max(size - 1, 8)),
            "title": tkfont.Font(family=family, size=size + 6, weight="bold"),
            "heading": tkfont.Font(family=family, size=size + 2, weight="bold"),
            "tile": tkfont.Font(family=family, size=size + 10, weight="bold"),
            "mono": tkfont.nametofont("TkFixedFont"),
        }

    def apply(self):
        c = self.c
        if not self.fonts:
            self._setup_fonts()
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.configure(bg=c["bg"])
        self.root.option_add("*tearOff", False)
        # Classic Tk widgets (menus, listboxes, text) don't follow ttk styles.
        for opt, val in (("*Menu.background", c["surface"]), ("*Menu.foreground", c["fg"]),
                         ("*Menu.activeBackground", c["select"]), ("*Menu.activeForeground", c["select_fg"]),
                         ("*Listbox.background", c["entry"]), ("*Listbox.foreground", c["fg"]),
                         ("*Text.background", c["entry"]), ("*Text.foreground", c["fg"]),
                         ("*TCombobox*Listbox.background", c["entry"]),
                         ("*TCombobox*Listbox.foreground", c["fg"]),
                         ("*TCombobox*Listbox.selectBackground", c["select"]),
                         ("*TCombobox*Listbox.selectForeground", c["select_fg"])):
            self.root.option_add(opt, val)

        style.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["entry"],
                        bordercolor=c["border"], darkcolor=c["bg"], lightcolor=c["bg"],
                        troughcolor=c["surface"], focuscolor=c["accent"], selectbackground=c["select"],
                        selectforeground=c["select_fg"], insertcolor=c["fg"], font=self.fonts["normal"])
        style.map(".", foreground=[("disabled", c["muted"])])
        style.configure("TFrame", background=c["bg"])
        style.configure("Surface.TFrame", background=c["surface"])
        style.configure("Toolbar.TFrame", background=c["surface"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("Surface.TLabel", background=c["surface"])
        style.configure("Muted.TLabel", foreground=c["muted"])
        style.configure("SurfaceMuted.TLabel", background=c["surface"], foreground=c["muted"])
        style.configure("Title.TLabel", font=self.fonts["title"])
        style.configure("Heading.TLabel", font=self.fonts["heading"])
        style.configure("Status.TLabel", background=c["surface"], foreground=c["muted"])
        style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"])
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"], font=self.fonts["bold"])

        style.configure("TButton", background=c["surface2"], foreground=c["fg"], bordercolor=c["border"],
                        padding=(10, 5), relief="flat", focuscolor=c["surface2"])
        style.map("TButton", background=[("disabled", c["surface"]), ("pressed", c["select"]),
                                         ("active", c["border"])],
                  foreground=[("disabled", c["muted"])])
        style.configure("Accent.TButton", background=c["accent"], foreground=c["accent_fg"],
                        bordercolor=c["accent"], font=self.fonts["bold"], focuscolor=c["accent"])
        style.map("Accent.TButton", background=[("disabled", c["surface2"]), ("pressed", c["accent"]),
                                                ("active", c["accent_hover"])],
                  foreground=[("disabled", c["muted"])])
        style.configure("Danger.TButton", foreground=c["danger"])
        style.configure("Toolbar.TButton", background=c["surface"], bordercolor=c["surface"], padding=(10, 6))
        style.map("Toolbar.TButton", background=[("pressed", c["select"]), ("active", c["surface2"])])
        style.configure("TMenubutton", background=c["surface"], foreground=c["fg"], bordercolor=c["surface"],
                        arrowcolor=c["fg"], padding=(10, 6))
        style.map("TMenubutton", background=[("active", c["surface2"])])

        style.configure("TEntry", fieldbackground=c["entry"], foreground=c["fg"], bordercolor=c["border"],
                        lightcolor=c["border"], darkcolor=c["border"], padding=4)
        style.map("TEntry", bordercolor=[("focus", c["accent"])], lightcolor=[("focus", c["accent"])])
        style.configure("TSpinbox", fieldbackground=c["entry"], foreground=c["fg"], bordercolor=c["border"],
                        arrowcolor=c["fg"], background=c["surface2"], padding=3)
        style.configure("TCombobox", fieldbackground=c["entry"], foreground=c["fg"], background=c["surface2"],
                        bordercolor=c["border"], arrowcolor=c["fg"], padding=3)
        style.map("TCombobox", fieldbackground=[("readonly", c["entry"])],
                  foreground=[("readonly", c["fg"])], selectbackground=[("readonly", c["entry"])],
                  selectforeground=[("readonly", c["fg"])])
        style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"], indicatorbackground=c["entry"],
                        indicatorforeground=c["accent"])
        style.map("TCheckbutton", background=[("active", c["bg"])],
                  indicatorbackground=[("selected", c["accent"]), ("active", c["surface2"])])
        style.configure("TRadiobutton", background=c["bg"], foreground=c["fg"], indicatorbackground=c["entry"])
        style.map("TRadiobutton", background=[("active", c["bg"])],
                  indicatorbackground=[("selected", c["accent"]), ("active", c["surface2"])])

        style.configure("TNotebook", background=c["bg"], bordercolor=c["border"], tabmargins=(4, 4, 4, 0))
        style.configure("TNotebook.Tab", background=c["surface"], foreground=c["muted"], padding=(14, 6),
                        bordercolor=c["border"])
        style.map("TNotebook.Tab", background=[("selected", c["surface2"])],
                  foreground=[("selected", c["fg"])], expand=[("selected", (0, 0, 0, 0))])

        style.configure("Treeview", background=c["entry"], fieldbackground=c["entry"], foreground=c["fg"],
                        bordercolor=c["border"], rowheight=int(self.fonts["normal"].metrics("linespace") * 1.7))
        style.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", c["select_fg"])])
        style.configure("Treeview.Heading", background=c["surface2"], foreground=c["fg"], bordercolor=c["border"],
                        relief="flat", font=self.fonts["bold"], padding=4)
        style.map("Treeview.Heading", background=[("active", c["border"])])
        for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(sb, background=c["surface2"], troughcolor=c["bg"], bordercolor=c["bg"],
                            lightcolor=c["surface2"], darkcolor=c["surface2"], arrowcolor=c["muted"],
                            gripcount=0, arrowsize=12)
            style.map(sb, background=[("active", c["border"])])
        style.configure("TProgressbar", background=c["accent"], troughcolor=c["surface2"],
                        bordercolor=c["surface2"], lightcolor=c["accent"], darkcolor=c["accent"])
        style.configure("TPanedwindow", background=c["border"])
        style.configure("TSeparator", background=c["border"])

    def style_text(self, widget: tk.Text) -> None:
        c = self.c
        widget.configure(bg=c["entry"], fg=c["fg"], insertbackground=c["fg"], selectbackground=c["select"],
                         selectforeground=c["select_fg"], relief="flat", highlightthickness=1,
                         highlightbackground=c["border"], highlightcolor=c["accent"], borderwidth=0)

    def toplevel(self, win: tk.Toplevel) -> None:
        win.configure(bg=self.c["bg"])
