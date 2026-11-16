"""Main launcher window: instance grid, sidebar and status bar."""
from __future__ import annotations

import hashlib
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from .. import APP_NAME, __version__, accounts, launch
from ..accounts import AccountStore
from ..config import Config, Paths
from ..instances import Instance, InstanceManager
from ..net import Cancelled
from ..platform_utils import IS_MAC, IS_WINDOWS, human_duration, open_path
from .theme import Theme
from .widgets import TaskRunner, app_icon, bind_right_click, bind_wheel

TILE_W, TILE_H = 132, 128
ICON = 64
MAX_LOG_LINES = 20000


@dataclass
class RunningGame:
    proc: object
    started: float
    instance_id: str
    killed: bool = False


@dataclass
class InstanceLog:
    """Game output. `add` is thread-safe; lines reach the UI in batches via `flush`,
    so a chatty game can't flood the window with one redraw per line."""
    lines: list = field(default_factory=list)
    listeners: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, line: str) -> None:
        with self.lock:
            self.pending.append(line)

    def flush(self) -> None:
        with self.lock:
            if not self.pending:
                return
            batch, self.pending = self.pending, []
        self.lines.extend(batch)
        if len(self.lines) > MAX_LOG_LINES:
            del self.lines[:len(self.lines) - MAX_LOG_LINES]
        for fn in list(self.listeners):
            try:
                fn(batch)
            except tk.TclError:
                self.listeners.remove(fn)


def tile_color(name: str) -> str:
    colors = ["#3fa34d", "#3b82c4", "#c4823b", "#8e5bc4", "#c43b5e", "#3bb3c4", "#9aa33f", "#c45b3b"]
    return colors[int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(colors)]


class App:
    def __init__(self, paths: Paths | None = None):
        self.paths = (paths or Paths()).ensure()
        self.config = Config(self.paths)
        self.settings = self.config.settings
        self.accounts = AccountStore(self.paths)
        self.instances = InstanceManager(self.paths)

        self.root = tk.Tk(className="VanquishModManager")
        self.root.title(APP_NAME)
        self.root.minsize(820, 520)
        geo = self.settings.window_geometry.split("+")[0]
        self.root.geometry(geo if geo and "x" in geo else "1100x680")
        self.theme = Theme(self.root, self.settings.theme)
        self._set_window_icon()

        self.running: dict[str, RunningGame] = {}
        self.logs: dict[str, InstanceLog] = {}
        self.instance_windows: dict[str, tk.Toplevel] = {}
        self.selected: Optional[Instance] = None
        self._all: list[Instance] = []
        self._tiles: list[tuple[tuple[int, int, int, int], Instance]] = []
        self._tile_items: dict[str, tuple[int, int]] = {}
        self._cache: dict[str, Instance] = {}
        self._hover: Optional[str] = None

        self.tasks = TaskRunner(self.root, self._set_status)
        self._build()
        self._bind_shortcuts()
        self.refresh_instances()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.after(100, self._flush_logs)
        # Warm the version list cache in the background so "Add Instance" opens instantly.
        from .. import versions
        self.tasks.run(lambda p, c: versions.get_manifest(self.paths), quiet=True, on_error=lambda e: None)
        if IS_MAC:
            self.root.createcommand("::tk::mac::ShowPreferences", self.open_settings)
            self.root.createcommand("::tk::mac::Quit", self.quit)

    # ------------------------------------------------------------------ layout

    def _build(self):
        c = self.theme.c
        # Toolbar
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(6, 4))
        bar.pack(side="top", fill="x")
        ttk.Button(bar, text="+ Add Instance", style="Toolbar.TButton", command=self.new_instance).pack(side="left")
        folders = ttk.Menubutton(bar, text="Folders")
        fm = tk.Menu(folders)
        fm.add_command(label="Instances", command=lambda: self._open(self.paths.instances))
        fm.add_command(label="Launcher data", command=lambda: self._open(self.paths.root))
        fm.add_command(label="Java runtimes", command=lambda: self._open(self.paths.java))
        fm.add_command(label="Logs", command=lambda: self._open(self.paths.logs))
        folders["menu"] = fm
        folders.pack(side="left")
        ttk.Button(bar, text="Settings", style="Toolbar.TButton", command=self.open_settings).pack(side="left")
        help_btn = ttk.Menubutton(bar, text="Help")
        hm = tk.Menu(help_btn)
        hm.add_command(label="About", command=self.about)
        help_btn["menu"] = hm
        help_btn.pack(side="left")

        self._account_var = tk.StringVar()
        self.account_btn = ttk.Menubutton(bar, text="No account")
        self.account_menu = tk.Menu(self.account_btn, postcommand=self._fill_account_menu)
        self.account_btn["menu"] = self.account_menu
        self.account_btn.pack(side="right")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._redraw())
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var, width=22)
        self.search_entry.pack(side="right", padx=8)
        ttk.Label(bar, text="Filter:", style="SurfaceMuted.TLabel").pack(side="right")

        # Status bar
        status = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(8, 3))
        status.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.cancel_btn = ttk.Button(status, text="Cancel", command=lambda: self.tasks.cancel())
        self.progress = ttk.Progressbar(status, length=220, mode="determinate")
        self.playtime_var = tk.StringVar()
        ttk.Label(status, textvariable=self.playtime_var, style="Status.TLabel").pack(side="right")

        # Body
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=c["bg"], highlightthickness=0, borderwidth=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.sidebar = ttk.Frame(body, style="Surface.TFrame", padding=12, width=240)
        self.sidebar.pack(side="right", fill="y")
        self.sidebar.pack_propagate(False)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Return>", lambda e: self.launch_selected())
        self.canvas.bind("<Delete>", lambda e: self.delete_selected())
        bind_right_click(self.canvas, self._on_context)
        bind_wheel(self.canvas, self.canvas)
        self._build_sidebar()
        self._update_account_label()

    def _set_window_icon(self):
        """Use the bundled icon (icon.ico / icon.png); fall back to a drawn one."""
        assets = Path(__file__).resolve().parent.parent / "assets"
        try:
            if IS_WINDOWS and (assets / "icon.ico").exists():
                self.root.iconbitmap(default=str(assets / "icon.ico"))
                return
            self._icon = tk.PhotoImage(master=self.root, file=str(assets / "icon.png"))
        except (tk.TclError, OSError):
            self._icon = app_icon(self.root)
        self.root.iconphoto(True, self._icon)

    def _bind_shortcuts(self):
        mod = "Command" if IS_MAC else "Control"
        r = self.root
        r.bind_all(f"<{mod}-n>", lambda e: self.new_instance())
        r.bind_all(f"<{mod}-comma>", lambda e: self.open_settings())
        r.bind_all(f"<{mod}-q>", lambda e: self.quit())
        r.bind(f"<{mod}-f>", lambda e: self.search_entry.focus_set())
        r.bind("<F5>", lambda e: self.refresh_instances())
        for key, dx in (("Left", -1), ("Right", 1), ("Up", "up"), ("Down", "down")):
            self.canvas.bind(f"<{key}>", lambda e, d=dx: self._move_selection(d))

    def _move_selection(self, d):
        visible = [inst for _, inst in self._tiles]
        if not visible:
            return
        if self.selected is None or self.selected not in visible:
            self.select(visible[0])
            return
        idx = visible.index(self.selected)
        cols = max(1, (max(self.canvas.winfo_width(), TILE_W + 20) - 20) // TILE_W)
        step = {"up": -cols, "down": cols}.get(d, d)
        self.select(visible[max(0, min(len(visible) - 1, idx + step))])

    def _flush_logs(self):
        for log in list(self.logs.values()):
            log.flush()
        self.root.after(100, self._flush_logs)

    def _build_sidebar(self):
        sb = self.sidebar
        self.side_icon = tk.Canvas(sb, width=72, height=72, bg=self.theme.c["surface"], highlightthickness=0)
        self.side_icon.pack(anchor="w", pady=(0, 8))
        self.side_name = ttk.Label(sb, text="", style="Surface.TLabel", font=self.theme.fonts["heading"],
                                   wraplength=210, justify="left")
        self.side_name.pack(anchor="w")
        self.side_info = ttk.Label(sb, text="Select an instance", style="SurfaceMuted.TLabel",
                                   wraplength=210, justify="left")
        self.side_info.pack(anchor="w", pady=(2, 10))
        self.btn_launch = ttk.Button(sb, text="Launch", style="Accent.TButton", command=self.launch_selected)
        self.btn_launch.pack(fill="x", pady=(0, 4))
        self.btn_kill = ttk.Button(sb, text="Kill", command=self.kill_selected)
        self.btn_kill.pack(fill="x", pady=(0, 10))
        self.side_buttons = []
        for text, cmd in (("Edit...", self.edit_selected), ("Mods", lambda: self.edit_selected("Mods")),
                          ("Open folder", self.open_selected_folder), ("Copy...", self.copy_selected),
                          ("Rename...", self.rename_selected), ("Change group...", self.group_selected)):
            b = ttk.Button(sb, text=text, command=cmd)
            b.pack(fill="x", pady=2)
            self.side_buttons.append(b)
        self.btn_delete = ttk.Button(sb, text="Delete", style="Danger.TButton", command=self.delete_selected)
        self.btn_delete.pack(fill="x", pady=(10, 2))
        self.side_buttons.append(self.btn_delete)
        self._update_sidebar()

    # ------------------------------------------------------------------ status

    def _set_status(self, text: str, frac: Optional[float], busy: bool):
        self.status_var.set(text)
        if busy:
            if not self.progress.winfo_ismapped():
                self.progress.pack(side="left", padx=10)
                self.cancel_btn.pack(side="left")
            if frac is None:
                if str(self.progress.cget("mode")) != "indeterminate":
                    self.progress.configure(mode="indeterminate")
                    self.progress.start(12)
            else:
                if str(self.progress.cget("mode")) != "determinate":
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                self.progress["value"] = frac * 100
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.cancel_btn.pack_forget()

    # ------------------------------------------------------------------ instances grid

    def refresh_instances(self, select_id: str | None = None):
        # Keep one Instance object per instance so open windows always see current data.
        merged = []
        for fresh in self.instances.list():
            old = self._cache.get(fresh.id)
            if old is not None:
                old.__dict__.update(fresh.__dict__)
                merged.append(old)
            else:
                self._cache[fresh.id] = fresh
                merged.append(fresh)
        ids = {i.id for i in merged}
        for k in [k for k in self._cache if k not in ids]:
            del self._cache[k]
        self._all = merged
        sel = select_id or (self.selected.id if self.selected else None)
        self.selected = next((i for i in self._all if i.id == sel), None)
        self._redraw()
        self._update_sidebar()
        total = sum(i.total_play_seconds for i in self._all)
        self.playtime_var.set(f"{len(self._all)} instances · total played {human_duration(total)}"
                              if self._all else "")

    def _visible(self) -> list[Instance]:
        q = self.search_var.get().strip().lower()
        if not q:
            return self._all
        return [i for i in self._all if q in i.name.lower() or q in i.mc_version.lower()
                or q in i.group.lower() or q in i.loader]

    def _redraw(self):
        cv = self.canvas
        c = self.theme.c
        f = self.theme.fonts
        cv.delete("all")
        self._tiles = []
        self._tile_items = {}
        width = max(cv.winfo_width(), TILE_W + 20)
        items = self._visible()
        if not items:
            msg = ("No instances yet.\nClick \"+ Add Instance\" to create one." if not self._all
                   else "No instances match the filter.")
            cv.create_text(width // 2, 120, text=msg, fill=c["muted"], font=f["heading"], justify="center")
            cv.configure(scrollregion=(0, 0, width, 300))
            return
        cols = max(1, (width - 20) // TILE_W)
        y = 12
        groups: dict[str, list[Instance]] = {}
        for i in items:
            groups.setdefault(i.group or "", []).append(i)
        for gname in sorted(groups, key=lambda g: (g == "", g.lower())):
            members = groups[gname]
            if len(groups) > 1 or gname:
                cv.create_text(14, y + 10, text=gname or "Ungrouped", anchor="w", fill=c["muted"], font=f["bold"])
                cv.create_line(14, y + 22, width - 14, y + 22, fill=c["border"])
                y += 30
            for n, inst in enumerate(members):
                col, row = n % cols, n // cols
                x0 = 10 + col * TILE_W
                y0 = y + row * TILE_H
                self._draw_tile(inst, x0, y0)
            y += ((len(members) - 1) // cols + 1) * TILE_H + 10
        cv.configure(scrollregion=(0, 0, width, y + 10))

    def _draw_tile(self, inst: Instance, x0: int, y0: int):
        cv = self.canvas
        c = self.theme.c
        f = self.theme.fonts
        sel = self.selected is not None and self.selected.id == inst.id
        hover = self._hover == inst.id
        x1, y1 = x0 + TILE_W - 8, y0 + TILE_H - 8
        bg = c["select"] if sel else c["tile_hover"] if hover else c["bg"]
        rect = cv.create_rectangle(x0, y0, x1, y1, fill=bg, outline=c["accent"] if sel else bg, width=1)
        ix = x0 + (TILE_W - 8 - ICON) // 2
        iy = y0 + 8
        cv.create_rectangle(ix, iy, ix + ICON, iy + ICON, fill=tile_color(inst.name), outline="")
        cv.create_text(ix + ICON // 2, iy + ICON // 2, text=(inst.name[:1] or "?").upper(), fill="#ffffff",
                       font=f["tile"])
        if inst.id in self.running:
            cv.create_oval(ix + ICON - 14, iy + 4, ix + ICON - 4, iy + 14, fill="#5cff6a", outline="#1e1f22")
        if inst.loader != "vanilla":
            cv.create_rectangle(ix, iy + ICON - 14, ix + ICON, iy + ICON, fill="#000000", outline="", stipple="gray50")
            cv.create_text(ix + ICON // 2, iy + ICON - 7, text=inst.loader.capitalize(), fill="#ffffff", font=f["small"])
        name = inst.name if len(inst.name) <= 34 else inst.name[:32] + "..."
        label = cv.create_text(x0 + (TILE_W - 8) // 2, iy + ICON + 6, text=name, anchor="n", width=TILE_W - 16,
                               fill=c["select_fg"] if sel else c["fg"], font=f["normal"], justify="center")
        self._tiles.append(((x0, y0, x1, y1), inst))
        self._tile_items[inst.id] = (rect, label)

    def _paint_tile(self, inst_id: Optional[str]):
        """Recolour one tile in place (much cheaper than redrawing the whole grid)."""
        items = self._tile_items.get(inst_id or "")
        if not items:
            return
        c = self.theme.c
        sel = self.selected is not None and self.selected.id == inst_id
        bg = c["select"] if sel else c["tile_hover"] if self._hover == inst_id else c["bg"]
        self.canvas.itemconfigure(items[0], fill=bg, outline=c["accent"] if sel else bg)
        self.canvas.itemconfigure(items[1], fill=c["select_fg"] if sel else c["fg"])

    def _hit(self, event) -> Optional[Instance]:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for (x0, y0, x1, y1), inst in self._tiles:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return inst
        return None

    def _on_click(self, event):
        self.canvas.focus_set()
        self.select(self._hit(event))

    def _on_double(self, event):
        inst = self._hit(event)
        if inst:
            self.select(inst)
            self.launch_selected()

    def _on_motion(self, event):
        inst = self._hit(event)
        hid = inst.id if inst else None
        if hid != self._hover:
            old, self._hover = self._hover, hid
            self._paint_tile(old)
            self._paint_tile(hid)

    def _on_context(self, event):
        inst = self._hit(event)
        menu = tk.Menu(self.root)
        if inst:
            self.select(inst)
            running = inst.id in self.running
            menu.add_command(label="Launch", command=self.launch_selected,
                             state="disabled" if running else "normal")
            if running:
                menu.add_command(label="Kill", command=self.kill_selected)
            menu.add_separator()
            menu.add_command(label="Edit...", command=self.edit_selected)
            menu.add_command(label="Mods...", command=lambda: self.edit_selected("Mods"))
            menu.add_command(label="Open folder", command=self.open_selected_folder)
            menu.add_command(label="Copy...", command=self.copy_selected)
            menu.add_command(label="Rename...", command=self.rename_selected)
            menu.add_command(label="Change group...", command=self.group_selected)
            menu.add_separator()
            menu.add_command(label="Delete", command=self.delete_selected)
        else:
            menu.add_command(label="Add instance...", command=self.new_instance)
            menu.add_command(label="Refresh", command=self.refresh_instances)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def select(self, inst: Optional[Instance]):
        old = self.selected.id if self.selected else None
        self.selected = inst
        self._paint_tile(old)
        self._paint_tile(inst.id if inst else None)
        if inst is not None:
            for (x0, y0, x1, y1), i in self._tiles:  # keep the selection on screen
                if i is inst:
                    top, bottom = self.canvas.canvasy(0), self.canvas.canvasy(self.canvas.winfo_height())
                    region = float(self.canvas.cget("scrollregion").split()[-1] or 1)
                    if y0 < top:
                        self.canvas.yview_moveto(max(0.0, (y0 - 10) / region))
                    elif y1 > bottom:
                        self.canvas.yview_moveto(max(0.0, (y1 + 10 - self.canvas.winfo_height()) / region))
                    break
        self._update_sidebar()

    def _update_sidebar(self):
        inst = self.selected
        state = "normal" if inst else "disabled"
        for b in self.side_buttons:
            b.configure(state=state)
        self.side_icon.delete("all")
        if not inst:
            self.side_icon.pack_forget()
            self.side_name.configure(text="")
            self.side_info.configure(text="Select an instance")
            self.btn_launch.configure(state="disabled")
            self.btn_kill.configure(state="disabled")
            return
        running = inst.id in self.running
        if not self.side_icon.winfo_ismapped():
            self.side_icon.pack(anchor="w", pady=(0, 8), before=self.side_name)
        self.side_icon.create_rectangle(0, 0, 72, 72, fill=tile_color(inst.name), outline="")
        self.side_icon.create_text(36, 36, text=(inst.name[:1] or "?").upper(), fill="#ffffff",
                                   font=self.theme.fonts["tile"])
        if running:
            self.side_icon.create_oval(56, 4, 68, 16, fill="#5cff6a", outline="")
        self.side_name.configure(text=inst.name)
        played = (time.strftime("%Y-%m-%d %H:%M", time.localtime(inst.last_played))
                  if inst.last_played else "never")
        lines = [inst.display_version, f"Last played: {played}",
                 f"Play time: {human_duration(inst.total_play_seconds)}"]
        if inst.group:
            lines.append(f"Group: {inst.group}")
        if running:
            lines.append("Running")
        self.side_info.configure(text="\n".join(lines))
        self.btn_launch.configure(state="disabled" if running else "normal",
                                  text="Running..." if running else "Launch")
        self.btn_kill.configure(state="normal" if running else "disabled")
        self.btn_delete.configure(state="disabled" if running else "normal")

    # ------------------------------------------------------------------ actions

    def _open(self, path):
        try:
            path.mkdir(parents=True, exist_ok=True)
            open_path(path)
        except Exception as e:
            messagebox.showerror("Could not open folder", str(e), parent=self.root)

    def new_instance(self):
        from .dialogs import NewInstanceDialog
        NewInstanceDialog(self).show()

    def open_settings(self):
        from .dialogs import SettingsDialog
        SettingsDialog(self).show()

    def manage_accounts(self):
        from .dialogs import AccountsDialog
        AccountsDialog(self).show()

    def about(self):
        messagebox.showinfo("About", f"{APP_NAME} {__version__}\n\nA lightweight instance-based Minecraft "
                            "launcher and mod manager.\n\nData folder:\n" + str(self.paths.root),
                            parent=self.root)

    def edit_selected(self, tab: str = "Log"):
        if not self.selected:
            return
        self.open_instance_window(self.selected, tab)

    def open_instance_window(self, inst: Instance, tab: str = "Log"):
        from .instance_window import InstanceWindow
        win = self.instance_windows.get(inst.id)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.select_tab(tab)  # type: ignore[attr-defined]
            return
        self.instance_windows[inst.id] = InstanceWindow(self, inst, tab)

    def open_selected_folder(self):
        if self.selected:
            self._open(self.selected.game_dir)

    def rename_selected(self):
        inst = self.selected
        if not inst:
            return
        name = simpledialog.askstring("Rename instance", "New name:", initialvalue=inst.name, parent=self.root)
        if name and name.strip():
            inst.name = name.strip()
            inst.save()
            self.refresh_instances(inst.id)

    def group_selected(self):
        inst = self.selected
        if not inst:
            return
        groups = sorted({i.group for i in self._all if i.group})
        hint = f"\nExisting groups: {', '.join(groups)}" if groups else ""
        name = simpledialog.askstring("Change group", "Group name (empty for none):" + hint,
                                      initialvalue=inst.group, parent=self.root)
        if name is not None:
            inst.group = name.strip()
            inst.save()
            self.refresh_instances(inst.id)

    def copy_selected(self):
        inst = self.selected
        if not inst:
            return
        name = simpledialog.askstring("Copy instance", "Name for the copy:", initialvalue=f"{inst.name} (copy)",
                                      parent=self.root)
        if not name:
            return
        saves = messagebox.askyesno("Copy instance", "Also copy worlds (saves)?", parent=self.root)
        self.tasks.run(lambda p, c: self.instances.copy(inst, name.strip(), saves),
                       lambda new: self.refresh_instances(new.id), label=f"Copying {inst.name}...")

    def delete_selected(self):
        inst = self.selected
        if not inst or inst.id in self.running:
            return
        if not messagebox.askyesno("Delete instance",
                                   f"Delete '{inst.name}' and ALL of its files, including worlds?\n\n"
                                   "This cannot be undone.", icon="warning", parent=self.root):
            return
        win = self.instance_windows.pop(inst.id, None)
        if win is not None and win.winfo_exists():
            win.destroy()
        try:
            self.instances.delete(inst)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e), parent=self.root)
        self.selected = None
        self.refresh_instances()

    # ------------------------------------------------------------------ accounts

    def _update_account_label(self):
        acc = self.accounts.default()
        self.account_btn.configure(text=acc.label if acc else "No account")

    def _fill_account_menu(self):
        m = self.account_menu
        m.delete(0, "end")
        default = self.accounts.default()
        self._account_var.set(default.uuid if default else "")
        for acc in self.accounts.accounts:
            m.add_radiobutton(label=acc.label, value=acc.uuid, variable=self._account_var,
                              command=lambda a=acc: (self.accounts.set_default(a), self._update_account_label()))
        if self.accounts.accounts:
            m.add_separator()
        m.add_command(label="Manage accounts...", command=self.manage_accounts)

    # ------------------------------------------------------------------ launching

    def log_for(self, inst: Instance) -> InstanceLog:
        return self.logs.setdefault(inst.id, InstanceLog())

    def launch_selected(self):
        if self.selected:
            self.launch(self.selected)

    def launch(self, inst: Instance):
        if inst.id in self.running:
            return
        acc = self.accounts.default()
        if acc is None:
            if messagebox.askyesno("No account", "You need an account to play.\n\nAdd one now?", parent=self.root):
                self.manage_accounts()
            return
        log = self.log_for(inst)
        log.add(f"--- {APP_NAME} {__version__}: preparing {inst.name} ({inst.display_version}) ---")
        settings = self.settings
        client_id = settings.msa_client_id

        def work(progress, cancel):
            def prog(text, frac=None):
                progress(text, frac)
                log.add(f"[launcher] {text}")
            account = acc
            if account.kind == "msa":
                prog("Refreshing Microsoft login...")
                account = accounts.refresh(account, client_id)
                if account is not acc:
                    self.tasks.post(self.accounts.add, account)
            cmd = launch.prepare(self.paths, inst, account, settings, prog, cancel)
            return cmd, account

        def done(res):
            cmd, account = res
            log.add("[launcher] Java command: " + launch.censor(cmd, account))
            try:
                proc = launch.start(cmd, inst.game_dir, log.add,
                                    lambda code: self.tasks.post(self._game_exited, inst, code))
            except OSError as e:
                messagebox.showerror("Launch failed", str(e), parent=self.root)
                return
            self.running[inst.id] = RunningGame(proc, time.time(), inst.id)
            inst.last_played = time.time()
            inst.save()
            self._update_sidebar()
            self._redraw()
            self.status_var.set(f"{inst.name} is running")
            if settings.close_on_launch:
                self.root.withdraw()

        def failed(e):
            if isinstance(e, Cancelled):
                log.add("[launcher] Launch cancelled")
                return
            log.add(f"[launcher] Launch failed: {e}")
            if isinstance(e, accounts.AuthError):
                messagebox.showerror("Login problem", str(e), parent=self.root)
            else:
                messagebox.showerror("Launch failed", str(e), parent=self.root)

        self.open_instance_window(inst, "Log")
        self.tasks.run(work, done, failed, label=f"Preparing {inst.name}...")

    def _game_exited(self, inst: Instance, code: int):
        rg = self.running.pop(inst.id, None)
        log = self.log_for(inst)
        log.add(f"[launcher] Game exited with code {code}")
        # Reload from disk so edits made while running are kept, then add the play time.
        fresh = Instance.load(inst.root)
        if fresh is not None:
            inst.__dict__.update(fresh.__dict__)
        if rg and inst.root.exists():
            inst.total_play_seconds += time.time() - rg.started
            inst.last_played = time.time()
            inst.save()
        if self.settings.close_on_launch and not self.running:
            self.root.deiconify()
        self.refresh_instances()
        if code != 0 and rg and not rg.killed:
            messagebox.showwarning("Minecraft crashed",
                                   f"{inst.name} stopped unexpectedly (exit code {code}).\n"
                                   "Check the Log tab for details.", parent=self.root)

    def kill_selected(self):
        inst = self.selected
        if not inst or inst.id not in self.running:
            return
        if messagebox.askyesno("Kill game", f"Force-stop {inst.name}? Unsaved progress will be lost.",
                               parent=self.root):
            try:
                self.running[inst.id].killed = True
                self.running[inst.id].proc.kill()  # type: ignore[attr-defined]
            except Exception:
                pass

    # ------------------------------------------------------------------ lifecycle

    def apply_theme(self):
        self.theme = Theme(self.root, self.settings.theme)
        self.canvas.configure(bg=self.theme.c["bg"])
        self._redraw()

    def quit(self):
        if self.running and not messagebox.askyesno(
                "Quit", "Minecraft is still running. Close the launcher anyway?\n(The game keeps running.)",
                parent=self.root):
            return
        try:
            self.settings.window_geometry = self.root.geometry().split("+")[0]
            self.config.save()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    if IS_WINDOWS:
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = App()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
