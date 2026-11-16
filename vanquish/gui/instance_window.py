"""Per-instance editor window with Prism-style tabs."""
from __future__ import annotations

import shutil
import time
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import launch, modrinth, mods
from ..instances import Instance
from ..platform_utils import human_size, open_path
from .dialogs import LoaderPicker, ModrinthBrowser, VersionList
from .widgets import bind_right_click, make_tree


class InstanceWindow(tk.Toplevel):
    TABS = ["Log", "Version", "Mods", "Resource packs", "Shader packs", "Worlds", "Settings", "Notes"]

    def __init__(self, app, inst: Instance, tab: str = "Log"):
        super().__init__(app.root)
        self.app = app
        self.inst = inst
        app.theme.toplevel(self)
        self.title(f"{inst.name} - Edit instance")
        self.geometry("960x620")
        self.minsize(720, 460)
        self.protocol("WM_DELETE_WINDOW", self._close)

        head = ttk.Frame(self, padding=(12, 10, 12, 0))
        head.pack(fill="x")
        self.h_title = ttk.Label(head, text=inst.name, style="Title.TLabel")
        self.h_title.pack(side="left")
        self.h_ver = ttk.Label(head, text=inst.display_version, style="Muted.TLabel")
        self.h_ver.pack(side="left", padx=12, pady=(6, 0))
        ttk.Button(head, text="Launch", style="Accent.TButton",
                   command=lambda: app.launch(self.inst)).pack(side="right")
        ttk.Button(head, text="Kill", command=self._kill).pack(side="right", padx=6)
        ttk.Button(head, text="Folder", command=lambda: self._open(inst.game_dir)).pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs: dict[str, ttk.Frame] = {}
        self.log_tab = LogTab(self.nb, self)
        self._add("Log", self.log_tab)
        self._add("Version", VersionTab(self.nb, self))
        self._add("Mods", ContentTab(self.nb, self, "mods"))
        self._add("Resource packs", ContentTab(self.nb, self, "resourcepacks"))
        self._add("Shader packs", ContentTab(self.nb, self, "shaderpacks"))
        self._add("Worlds", WorldsTab(self.nb, self))
        self._add("Settings", SettingsTab(self.nb, self))
        self._add("Notes", NotesTab(self.nb, self))
        self.nb.bind("<<NotebookTabChanged>>", self._tab_changed)
        self.select_tab(tab)

    def _add(self, name, frame):
        self.tabs[name] = frame
        self.nb.add(frame, text=name)

    def select_tab(self, name: str):
        if name in self.tabs:
            self.nb.select(self.tabs[name])

    def _tab_changed(self, _=None):
        tab = self.nb.nametowidget(self.nb.select())
        if hasattr(tab, "refresh"):
            tab.refresh()

    def _open(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        open_path(path)

    def _kill(self):
        self.app.select(self.inst)
        self.app.kill_selected()

    def instance_changed(self):
        self.title(f"{self.inst.name} - Edit instance")
        self.h_title.configure(text=self.inst.name)
        self.h_ver.configure(text=self.inst.display_version)
        self.app.refresh_instances(self.inst.id)

    def _close(self):
        self.log_tab.detach()
        self.app.instance_windows.pop(self.inst.id, None)
        self.destroy()


# ---------------------------------------------------------------------- log

class LogTab(ttk.Frame):
    def __init__(self, parent, win: InstanceWindow):
        super().__init__(parent, padding=6)
        self.win = win
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 4))
        self.autoscroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Auto-scroll", variable=self.autoscroll).pack(side="left")
        ttk.Button(bar, text="Copy all", command=self.copy).pack(side="right")
        ttk.Button(bar, text="Clear", command=self.clear).pack(side="right", padx=4)
        ttk.Button(bar, text="Crash reports",
                   command=lambda: win._open(win.inst.game_dir / "crash-reports")).pack(side="right")
        ttk.Button(bar, text="Game logs", command=lambda: win._open(win.inst.game_dir / "logs")).pack(side="right", padx=4)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, wrap="none", font=win.app.theme.fonts["mono"], undo=False)
        win.app.theme.style_text(self.text)
        c = win.app.theme.c
        self.text.tag_configure("warn", foreground=c["warn"])
        self.text.tag_configure("error", foreground=c["danger"])
        self.text.tag_configure("launcher", foreground=c["accent"])
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        xs = ttk.Scrollbar(frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.text.bind("<Key>", self._readonly)
        self.log = win.app.log_for(win.inst)
        for line in self.log.lines:
            self._append(line, scroll=False)
        self.text.see("end")
        self.log.listeners.append(self._append)

    @staticmethod
    def _readonly(e):
        if (e.state & 0x4 or e.state & 0x8) and e.keysym.lower() in ("c", "a"):
            return None
        return "break"

    def _append(self, line: str, scroll: bool = True):
        tag = ()
        if line.startswith("[launcher]") or line.startswith("---"):
            tag = ("launcher",)
        elif "/ERROR]" in line or "ERROR" in line[:40] or "Exception" in line:
            tag = ("error",)
        elif "/WARN]" in line or "WARN" in line[:40]:
            tag = ("warn",)
        self.text.insert("end", line + "\n", tag)
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > 20000:
            self.text.delete("1.0", f"{lines - 20000}.0")
        if scroll and self.autoscroll.get():
            self.text.see("end")

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))

    def clear(self):
        self.text.delete("1.0", "end")
        self.log.lines.clear()

    def detach(self):
        if self._append in self.log.listeners:
            self.log.listeners.remove(self._append)


# ---------------------------------------------------------------------- version

class VersionTab(ttk.Frame):
    def __init__(self, parent, win: InstanceWindow):
        super().__init__(parent, padding=10)
        self.win = win
        inst = win.inst
        self.current = ttk.Label(self, text="", style="Heading.TLabel")
        self.current.pack(anchor="w")
        ttk.Label(self, text="Pick a different Minecraft version or mod loader below. Mods are not changed "
                             "automatically - check they support the new version.",
                  style="Muted.TLabel", wraplength=800, justify="left").pack(anchor="w", pady=(2, 8))
        btns = ttk.Frame(self)
        btns.pack(side="bottom", fill="x")
        self.loader = LoaderPicker(self, win.app, inst.loader, inst.loader_version)
        self.loader.pack(side="bottom", fill="x", pady=8)
        self.versions = VersionList(self, win.app, on_select=self.loader.set_mc_version, initial=inst.mc_version)
        self.versions.pack(fill="both", expand=True)
        ttk.Button(btns, text="Apply", style="Accent.TButton", command=self.apply).pack(side="right")
        ttk.Button(btns, text="Re-download game files", command=self.redownload).pack(side="left")
        self.refresh()

    def refresh(self):
        self.current.configure(text=f"Current: {self.win.inst.display_version}")

    def apply(self):
        inst = self.win.inst
        if inst.id in self.win.app.running:
            messagebox.showwarning("Version", "Close the game first.", parent=self.win)
            return
        mc = self.versions.selected() or inst.mc_version
        loader, lv = self.loader.value()
        if loader != "vanilla" and not lv:
            messagebox.showwarning("Version", "No loader version selected.", parent=self.win)
            return
        if (mc, loader, lv) == (inst.mc_version, inst.loader, inst.loader_version):
            return
        inst.mc_version, inst.loader, inst.loader_version = mc, loader, lv
        inst.version_id = ""
        inst.save()
        self.refresh()
        self.win.instance_changed()
        app = self.win.app
        app.tasks.run(lambda p, c: launch.ensure_installed(app.paths, inst, p, c, app.settings.download_workers),
                      label=f"Downloading {inst.display_version}...", parent=self.win)

    def redownload(self):
        app = self.win.app
        inst = self.win.inst
        from .. import versions as v

        def work(p, c):
            vid = inst.version_id or inst.mc_version
            for d in {vid, inst.mc_version}:
                j = v.version_json_path(app.paths, d)
                j.unlink(missing_ok=True)
            inst.version_id = ""
            return launch.ensure_installed(app.paths, inst, p, c, app.settings.download_workers)
        app.tasks.run(work, lambda _: messagebox.showinfo("Version", "Game files verified.", parent=self.win),
                      label="Re-downloading game files...", parent=self.win)


# ---------------------------------------------------------------------- mods / packs

class ContentTab(ttk.Frame):
    """Mods, resource packs and shader packs: list, enable/disable, add, remove, download."""

    TYPES = {"mods": ("mod", "mods_dir"), "resourcepacks": ("resourcepack", "resourcepacks_dir"),
             "shaderpacks": ("shader", "shaderpacks_dir")}

    def __init__(self, parent, win: InstanceWindow, kind: str):
        super().__init__(parent, padding=6)
        self.win = win
        self.kind = kind
        self.ptype, attr = self.TYPES[kind]
        self.folder: Path = getattr(win.inst, attr)
        self.items: dict[str, mods.ModFile] = {}
        self.updates: dict[Path, dict] = {}

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 4))
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.refresh(rescan=False))
        ttk.Label(bar, text="Filter:").pack(side="left")
        ttk.Entry(bar, textvariable=self.filter, width=24).pack(side="left", padx=6)
        self.summary = ttk.Label(bar, text="", style="Muted.TLabel")
        self.summary.pack(side="left", padx=6)

        self.detail = ttk.Label(self, text="", style="Muted.TLabel", wraplength=860, justify="left")
        self.detail.pack(side="bottom", fill="x", pady=(4, 0))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        cols = [("on", "On", 46), ("name", "Name", 240), ("version", "Version", 120), ("file", "File", 240)]
        if kind == "mods":
            cols.append(("loader", "Loader", 90))
        cols.append(("note", "", 120))
        side = ttk.Frame(body, padding=(8, 0, 0, 0))
        side.pack(side="right", fill="y")
        frame, self.tree = make_tree(body, cols)
        self.tree.column("on", anchor="center", stretch=False)
        frame.pack(side="left", fill="both", expand=True)
        c = win.app.theme.c
        self.tree.tag_configure("disabled", foreground=c["muted"])
        self.tree.tag_configure("problem", foreground=c["warn"])
        self.tree.tag_configure("update", foreground=c["accent"])
        self.tree.bind("<Double-Button-1>", lambda e: self.toggle())
        self.tree.bind("<space>", lambda e: self.toggle())
        self.tree.bind("<Delete>", lambda e: self.remove())
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        bind_right_click(self.tree, self._context)
        label = {"mods": "Download mods", "resourcepacks": "Download packs", "shaderpacks": "Download shaders"}[kind]
        ttk.Button(side, text=label, style="Accent.TButton", command=self.browse).pack(fill="x", pady=2)
        ttk.Button(side, text="Add file...", command=self.add_file).pack(fill="x", pady=2)
        ttk.Button(side, text="Enable", command=lambda: self.set_enabled(True)).pack(fill="x", pady=(10, 2))
        ttk.Button(side, text="Disable", command=lambda: self.set_enabled(False)).pack(fill="x", pady=2)
        ttk.Button(side, text="Remove", style="Danger.TButton", command=self.remove).pack(fill="x", pady=2)
        if kind == "mods":
            ttk.Button(side, text="Check for updates", command=self.check_updates).pack(fill="x", pady=(10, 2))
            self.update_btn = ttk.Button(side, text="Update all", command=self.update_all, state="disabled")
            self.update_btn.pack(fill="x", pady=2)
        ttk.Button(side, text="Open folder", command=lambda: win._open(self.folder)).pack(fill="x", pady=(10, 2))
        ttk.Button(side, text="Refresh", command=self.refresh).pack(fill="x", pady=2)
        self._scanned: list[mods.ModFile] = []
        self.refresh()

    def refresh(self, rescan: bool = True):
        if rescan:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._scanned = mods.list_content(self.folder, self.kind)
        q = self.filter.get().strip().lower()
        sel = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        loader = self.win.inst.loader
        dupes = mods.find_duplicates(self._scanned) if self.kind == "mods" else {}
        enabled = 0
        for m in self._scanned:
            if m.enabled:
                enabled += 1
            if q and q not in m.name.lower() and q not in m.filename.lower():
                continue
            iid = m.path.name
            self.items[iid] = m
            note, tags = "", ()
            if not m.enabled:
                tags = ("disabled",)
            if self.kind == "mods":
                if m.enabled and mods.loader_mismatch(m, loader):
                    note, tags = f"needs {'/'.join(m.loaders) or '?'}", ("problem",)
                elif m.mod_id in dupes:
                    note, tags = "duplicate", ("problem",)
                if m.path in self.updates:
                    note, tags = "update: " + self.updates[m.path].get("version_number", "?"), ("update",)
            values = ["✔" if m.enabled else "", m.name, m.version, m.filename]
            if self.kind == "mods":
                values.append(", ".join(m.loaders))
            values.append(note)
            self.tree.insert("", "end", iid=iid, values=values, tags=tags)
        for s in sel:
            if self.tree.exists(s):
                self.tree.selection_add(s)
        self.summary.configure(text=f"{enabled} enabled of {len(self._scanned)}")

    def _selected(self) -> list[mods.ModFile]:
        return [self.items[i] for i in self.tree.selection() if i in self.items]

    def _show_detail(self, _=None):
        sel = self._selected()
        if len(sel) != 1:
            self.detail.configure(text=f"{len(sel)} selected" if sel else "")
            return
        m = sel[0]
        parts = [m.name]
        if m.authors:
            parts.append(f"by {m.authors}")
        if m.mc_version:
            parts.append(f"Minecraft {m.mc_version}")
        try:
            parts.append(human_size(m.path.stat().st_size) if m.path.is_file() else "folder")
        except OSError:
            pass
        text = " · ".join(parts)
        if m.description:
            text += "\n" + m.description.strip()[:400]
        self.detail.configure(text=text)

    def _context(self, event):
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        menu = tk.Menu(self)
        menu.add_command(label="Enable", command=lambda: self.set_enabled(True))
        menu.add_command(label="Disable", command=lambda: self.set_enabled(False))
        menu.add_command(label="Remove", command=self.remove)
        menu.add_separator()
        menu.add_command(label="Open folder", command=lambda: self.win._open(self.folder))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def toggle(self):
        for m in self._selected():
            self._set(m, not m.enabled)
        self.refresh()

    def set_enabled(self, on: bool):
        for m in self._selected():
            self._set(m, on)
        self.refresh()

    def _set(self, m: mods.ModFile, on: bool):
        try:
            old = m.path
            mods.set_enabled(m, on)
            if old in self.updates:
                self.updates[m.path] = self.updates.pop(old)
        except OSError as e:
            messagebox.showerror("Error", str(e), parent=self.win)

    def remove(self):
        sel = self._selected()
        if not sel:
            return
        names = "\n".join(m.filename for m in sel[:10]) + ("\n..." if len(sel) > 10 else "")
        if not messagebox.askyesno("Remove", f"Delete these files?\n\n{names}", parent=self.win):
            return
        for m in sel:
            try:
                mods.remove(m)
            except OSError as e:
                messagebox.showerror("Error", str(e), parent=self.win)
        self.refresh()

    def add_file(self):
        types = {"mods": [("Mods", "*.jar"), ("All files", "*")],
                 "resourcepacks": [("Resource packs", "*.zip"), ("All files", "*")],
                 "shaderpacks": [("Shader packs", "*.zip"), ("All files", "*")]}[self.kind]
        files = filedialog.askopenfilenames(parent=self.win, title="Add files", filetypes=types)
        if files:
            try:
                mods.add_files(self.folder, [Path(f) for f in files])
            except OSError as e:
                messagebox.showerror("Error", str(e), parent=self.win)
            self.refresh()

    def browse(self):
        if self.kind == "mods" and self.win.inst.loader == "vanilla":
            if not messagebox.askyesno("Mods need a loader",
                                       "This instance is vanilla, so mods will not load. Install a mod loader "
                                       "(Fabric or Quilt) in the Version tab.\n\nBrowse mods anyway?",
                                       parent=self.win):
                return
        ModrinthBrowser(self.win.app, self.win.inst, self.ptype, on_installed=self.refresh, parent=self.win).show()

    def check_updates(self):
        inst = self.win.inst
        files = [m.path for m in self._scanned if m.path.is_file()]
        if not files:
            return

        def done(updates):
            self.updates = updates
            self.update_btn.configure(state="normal" if updates else "disabled")
            self.refresh(rescan=False)
            messagebox.showinfo("Updates", f"{len(updates)} update(s) available." if updates
                                else "All mods from Modrinth are up to date.", parent=self.win)
        self.win.app.tasks.run(lambda p, c: modrinth.check_updates(files, inst.mc_version, inst.loader), done,
                               label="Checking for mod updates...", parent=self.win)

    def update_all(self):
        updates = dict(self.updates)

        def work(p, c):
            n = 0
            for i, (path, ver) in enumerate(updates.items()):
                p(f"Updating {path.name}...", i / max(len(updates), 1))
                modrinth.apply_update(path, ver)
                n += 1
            return n

        def done(n):
            self.updates = {}
            self.update_btn.configure(state="disabled")
            self.refresh()
            messagebox.showinfo("Updates", f"Updated {n} mod(s).", parent=self.win)
        self.win.app.tasks.run(work, done, label="Updating mods...", parent=self.win)


# ---------------------------------------------------------------------- worlds

class WorldsTab(ttk.Frame):
    def __init__(self, parent, win: InstanceWindow):
        super().__init__(parent, padding=6)
        self.win = win
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        side = ttk.Frame(body, padding=(8, 0, 0, 0))
        side.pack(side="right", fill="y")
        frame, self.tree = make_tree(body, [("name", "World", 260), ("modified", "Last played", 150),
                                            ("size", "Size", 90)], selectmode="browse")
        frame.pack(side="left", fill="both", expand=True)
        ttk.Button(side, text="Open folder", command=self.open_world).pack(fill="x", pady=2)
        ttk.Button(side, text="Back up (zip)", command=self.backup).pack(fill="x", pady=2)
        ttk.Button(side, text="Import world (zip)...", command=self.import_zip).pack(fill="x", pady=2)
        ttk.Button(side, text="Delete", style="Danger.TButton", command=self.delete).pack(fill="x", pady=(10, 2))
        ttk.Button(side, text="Backups folder",
                   command=lambda: win._open(win.inst.root / "backups")).pack(fill="x", pady=(10, 2))
        ttk.Button(side, text="Refresh", command=self.refresh).pack(fill="x", pady=2)
        self.refresh()

    def _size(self, p: Path) -> int:
        total = 0
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
        return total

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        saves = self.win.inst.saves_dir
        if not saves.is_dir():
            return
        worlds = [d for d in saves.iterdir() if d.is_dir() and (d / "level.dat").exists()]
        worlds.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        for d in worlds:
            mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.stat().st_mtime))
            self.tree.insert("", "end", iid=d.name, values=(d.name, mtime, human_size(self._size(d))))

    def _sel(self) -> Path | None:
        s = self.tree.selection()
        return self.win.inst.saves_dir / s[0] if s else None

    def open_world(self):
        p = self._sel()
        self.win._open(p or self.win.inst.saves_dir)

    def backup(self):
        p = self._sel()
        if not p:
            return
        dest_dir = self.win.inst.root / "backups"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{p.name}-{time.strftime('%Y%m%d-%H%M%S')}.zip"

        def work(prog, c):
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in p.rglob("*"):
                    if f.is_file() and f.name != "session.lock":
                        zf.write(f, Path(p.name) / f.relative_to(p))
            return dest
        self.win.app.tasks.run(work, lambda d: messagebox.showinfo("Backup", f"Saved {d.name}", parent=self.win),
                               label=f"Backing up {p.name}...", parent=self.win)

    def import_zip(self):
        f = filedialog.askopenfilename(parent=self.win, title="Import world", filetypes=[("Zip", "*.zip")])
        if not f:
            return
        saves = self.win.inst.saves_dir

        def work(p, c):
            with zipfile.ZipFile(f) as zf:
                names = zf.namelist()
                lvl = next((n for n in names if n.endswith("level.dat")), None)
                if not lvl:
                    raise ValueError("This zip does not contain a Minecraft world (no level.dat).")
                prefix = lvl[:-len("level.dat")]
                name = Path(prefix).name or Path(f).stem
                target = saves / name
                n = 1
                while target.exists():
                    n += 1
                    target = saves / f"{name} ({n})"
                for m in zf.infolist():
                    if m.is_dir() or not m.filename.startswith(prefix):
                        continue
                    rel = m.filename[len(prefix):]
                    out = target / rel
                    if not str(out.resolve()).startswith(str(target.resolve())):
                        continue
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(m) as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        self.win.app.tasks.run(work, lambda _: self.refresh(), label="Importing world...", parent=self.win)

    def delete(self):
        p = self._sel()
        if not p:
            return
        if self.win.inst.id in self.win.app.running:
            messagebox.showwarning("Delete world", "Close the game first.", parent=self.win)
            return
        if messagebox.askyesno("Delete world", f"Permanently delete the world '{p.name}'?", icon="warning",
                               parent=self.win):
            shutil.rmtree(p, ignore_errors=True)
            self.refresh()


# ---------------------------------------------------------------------- settings

class SettingsTab(ttk.Frame):
    def __init__(self, parent, win: InstanceWindow):
        super().__init__(parent, padding=12)
        self.win = win
        inst = win.inst
        g = win.app.settings
        ttk.Label(self, text="Leave a field empty or 0 to use the global setting.", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        self.java = tk.StringVar(value=inst.java_path)
        ttk.Label(self, text="Java executable:").grid(row=1, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.java, width=60).grid(row=1, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Button(self, text="Browse...", command=self._browse).grid(row=1, column=3, sticky="w")
        self.min_mem = tk.IntVar(value=inst.min_memory)
        self.max_mem = tk.IntVar(value=inst.max_memory)
        ttk.Label(self, text="Min memory (MiB):").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(self, from_=0, to=65536, increment=256, textvariable=self.min_mem, width=8).grid(
            row=2, column=1, sticky="w", padx=6)
        ttk.Label(self, text=f"global: {g.min_memory}", style="Muted.TLabel").grid(row=2, column=2, sticky="w")
        ttk.Label(self, text="Max memory (MiB):").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Spinbox(self, from_=0, to=65536, increment=256, textvariable=self.max_mem, width=8).grid(
            row=3, column=1, sticky="w", padx=6)
        ttk.Label(self, text=f"global: {g.max_memory}", style="Muted.TLabel").grid(row=3, column=2, sticky="w")
        self.jvm = tk.StringVar(value=inst.jvm_args)
        ttk.Label(self, text="JVM arguments:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(self, textvariable=self.jvm).grid(row=4, column=1, columnspan=3, sticky="ew", padx=6)
        self.w = tk.IntVar(value=inst.window_width)
        self.h = tk.IntVar(value=inst.window_height)
        ttk.Label(self, text="Window size:").grid(row=5, column=0, sticky="w", pady=4)
        row = ttk.Frame(self)
        row.grid(row=5, column=1, sticky="w", padx=6)
        ttk.Spinbox(row, from_=0, to=7680, textvariable=self.w, width=6).pack(side="left")
        ttk.Label(row, text=" x ").pack(side="left")
        ttk.Spinbox(row, from_=0, to=4320, textvariable=self.h, width=6).pack(side="left")
        ttk.Button(self, text="Save", style="Accent.TButton", command=self.save).grid(
            row=6, column=3, sticky="e", pady=16)
        self.columnconfigure(2, weight=1)

    def _browse(self):
        f = filedialog.askopenfilename(parent=self.win, title="Choose the java executable")
        if f:
            self.java.set(f)

    def save(self):
        inst = self.win.inst
        try:
            vals = [int(v.get()) for v in (self.min_mem, self.max_mem, self.w, self.h)]
        except (tk.TclError, ValueError):
            messagebox.showerror("Settings", "Memory and window size must be numbers.", parent=self.win)
            return
        if vals[0] and vals[1] and vals[0] > vals[1]:
            messagebox.showerror("Settings", "Minimum memory cannot be larger than maximum.", parent=self.win)
            return
        inst.java_path = self.java.get().strip()
        inst.min_memory, inst.max_memory, inst.window_width, inst.window_height = vals
        inst.jvm_args = self.jvm.get().strip()
        inst.save()
        messagebox.showinfo("Settings", "Saved.", parent=self.win)


class NotesTab(ttk.Frame):
    def __init__(self, parent, win: InstanceWindow):
        super().__init__(parent, padding=6)
        self.win = win
        self.text = tk.Text(self, wrap="word", height=10)
        win.app.theme.style_text(self.text)
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", win.inst.notes)
        ttk.Button(self, text="Save notes", command=self.save).pack(anchor="e", pady=6)

    def save(self):
        self.win.inst.notes = self.text.get("1.0", "end-1c")
        self.win.inst.save()
