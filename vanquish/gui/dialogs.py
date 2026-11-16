"""Dialogs: new instance, settings, accounts and the Modrinth browser."""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .. import accounts, java, launch, loaders, modrinth, mrpack, net, versions
from ..instances import Instance
from ..platform_utils import human_size, open_path
from .widgets import Dialog, make_tree


# ====================================================================== version list

class VersionList(ttk.Frame):
    """Filterable list of Minecraft versions from Mojang's manifest."""

    def __init__(self, parent, app, on_select: Callable[[str], None] | None = None, initial: str = ""):
        super().__init__(parent)
        self.app = app
        self.on_select = on_select
        self.initial = initial
        self.manifest: dict = {}
        filt = ttk.Frame(self)
        filt.pack(fill="x", pady=(0, 4))
        self.v_release = tk.BooleanVar(value=True)
        self.v_snap = tk.BooleanVar(value=app.settings.show_snapshots)
        self.v_old = tk.BooleanVar(value=False)
        for text, var in (("Releases", self.v_release), ("Snapshots", self.v_snap), ("Beta / Alpha", self.v_old)):
            ttk.Checkbutton(filt, text=text, variable=var, command=self.fill).pack(side="left", padx=(0, 8))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.fill())
        ttk.Button(filt, text="Refresh", command=lambda: self.load(True)).pack(side="right")
        ttk.Entry(filt, textvariable=self.search, width=14).pack(side="right", padx=4)
        ttk.Label(filt, text="Search:").pack(side="right")
        frame, self.tree = make_tree(self, [("version", "Version", 140), ("type", "Type", 90),
                                            ("date", "Released", 110)], selectmode="browse")
        frame.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.status = ttk.Label(self, text="Loading versions...", style="Muted.TLabel")
        self.status.pack(anchor="w")
        self.load()

    def load(self, refresh: bool = False):
        self.status.configure(text="Loading versions...")

        def done(m):
            self.manifest = m
            self.fill()

        def err(e):
            self.status.configure(text=f"Could not load versions: {e}")

        self.app.tasks.run(lambda p, c: versions.get_manifest(self.app.paths, refresh), done, err,
                           label="Loading version list...")

    def fill(self):
        if not self.winfo_exists():
            return
        cur = self.selected()
        self.tree.delete(*self.tree.get_children())
        q = self.search.get().strip().lower()
        count = 0
        for v in self.manifest.get("versions", []):
            t = v.get("type")
            if (t == "release" and not self.v_release.get()) or (t == "snapshot" and not self.v_snap.get()) \
                    or (t in ("old_beta", "old_alpha") and not self.v_old.get()):
                continue
            if q and q not in v["id"].lower():
                continue
            self.tree.insert("", "end", iid=v["id"], values=(v["id"], t.replace("_", " "),
                                                            v.get("releaseTime", "")[:10]))
            count += 1
        self.status.configure(text=f"{count} versions")
        want = cur or self.initial or (self.manifest.get("latest") or {}).get("release")
        if want and self.tree.exists(want):
            self.tree.selection_set(want)
            self.tree.see(want)

    def selected(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else ""

    def _selected(self, _=None):
        if self.on_select and self.selected():
            self.on_select(self.selected())


class LoaderPicker(ttk.Frame):
    """Vanilla / Fabric / Quilt choice plus loader version."""

    def __init__(self, parent, app, loader: str = "vanilla", loader_version: str = ""):
        super().__init__(parent)
        self.app = app
        self.mc_version = ""
        self.loader = tk.StringVar(value=loader)
        self.version = tk.StringVar(value=loader_version)
        self._wanted = loader_version
        row = ttk.Frame(self)
        row.pack(fill="x")
        ttk.Label(row, text="Mod loader:").pack(side="left", padx=(0, 8))
        for key in loaders.LOADER_CHOICES:
            ttk.Radiobutton(row, text=loaders.LOADER_LABELS[key], value=key, variable=self.loader,
                            command=self.reload).pack(side="left", padx=(0, 8))
        row2 = ttk.Frame(self)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Label(row2, text="Loader version:").pack(side="left", padx=(0, 8))
        self.combo = ttk.Combobox(row2, textvariable=self.version, state="readonly", width=28)
        self.combo.pack(side="left")
        self.info = ttk.Label(row2, text="", style="Muted.TLabel")
        self.info.pack(side="left", padx=8)
        self._token = 0
        self.reload()

    def set_mc_version(self, v: str):
        if v != self.mc_version:
            self.mc_version = v
            self.reload()

    def reload(self):
        loader = self.loader.get()
        self._token += 1
        token = self._token
        if loader == "vanilla" or not self.mc_version:
            self.combo.configure(values=[], state="disabled")
            self.version.set("")
            self.info.configure(text="")
            return
        self.combo.configure(state="disabled")
        self.info.configure(text="Loading...")

        def done(vs):
            if token != self._token or not self.winfo_exists():
                return
            if not vs:
                self.combo.configure(values=[], state="disabled")
                self.version.set("")
                self.info.configure(text=f"{loaders.LOADER_LABELS[loader]} does not support {self.mc_version}")
                return
            labels = [v["version"] + ("" if v["stable"] else " (beta)") for v in vs]
            self.combo.configure(values=labels, state="readonly")
            pick = next((l for l in labels if l.split(" ")[0] == self._wanted), None)
            if pick is None:
                pick = next((l for l, v in zip(labels, vs) if v["stable"]), labels[0])
            self.version.set(pick)
            self.info.configure(text="")

        def err(e):
            if token == self._token and self.winfo_exists():
                self.info.configure(text=f"Could not load: {e}")

        self.app.tasks.run(lambda p, c: loaders.loader_versions(loader, self.mc_version), done, err, quiet=True)

    def value(self) -> tuple[str, str]:
        loader = self.loader.get()
        if loader == "vanilla":
            return "vanilla", ""
        return loader, self.version.get().split(" ")[0]


# ====================================================================== new instance

class NewInstanceDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "New Instance", modal=False)
        self.geometry("720x620")
        app_groups = sorted({i.group for i in app.instances.list() if i.group})
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        ttk.Label(top, text="Name:").grid(row=0, column=0, sticky="w")
        self.name = tk.StringVar()
        self._auto_name = ""
        ttk.Entry(top, textvariable=self.name).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(top, text="Group:").grid(row=0, column=2, sticky="w")
        self.group = tk.StringVar()
        ttk.Combobox(top, textvariable=self.group, values=app_groups, width=16).grid(row=0, column=3, sticky="w")
        top.columnconfigure(1, weight=1)

        self.nb = ttk.Notebook(self.body)
        self.nb.pack(fill="both", expand=True, pady=10)

        # Custom
        custom = ttk.Frame(self.nb, padding=8)
        self.nb.add(custom, text="Custom")
        imp = ttk.Frame(custom)
        imp.pack(side="bottom", fill="x", pady=(8, 0))
        self.loader = LoaderPicker(custom, app)
        self.loader.pack(side="bottom", fill="x", pady=(8, 0))
        self.versions = VersionList(custom, app, on_select=self._version_changed)
        self.versions.pack(fill="both", expand=True)
        self.loader.loader.trace_add("write", lambda *_: self._update_auto_name())
        self.copy_from = tk.StringVar()
        ttk.Label(imp, text="Copy mods/config/worlds from folder (optional):").pack(side="left")
        ttk.Entry(imp, textvariable=self.copy_from).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(imp, text="Browse...", command=self._browse_copy).pack(side="left")

        # Import .mrpack
        imp_tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(imp_tab, text="Import .mrpack")
        ttk.Label(imp_tab, text="Import a Modrinth modpack file (.mrpack). Fabric, Quilt and vanilla packs "
                                "are supported.", wraplength=600, justify="left").pack(anchor="w")
        row = ttk.Frame(imp_tab)
        row.pack(fill="x", pady=10)
        self.pack_path = tk.StringVar()
        ttk.Entry(row, textvariable=self.pack_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self._browse_pack).pack(side="left", padx=6)
        self.pack_info = ttk.Label(imp_tab, text="", style="Muted.TLabel", wraplength=600, justify="left")
        self.pack_info.pack(anchor="w")

        # Modrinth modpacks
        mr = ttk.Frame(self.nb, padding=8)
        self.nb.add(mr, text="Modrinth modpacks")
        srow = ttk.Frame(mr)
        srow.pack(fill="x")
        self.mp_query = tk.StringVar()
        e = ttk.Entry(srow, textvariable=self.mp_query)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda ev: self._search_packs())
        ttk.Button(srow, text="Search", command=self._search_packs).pack(side="left", padx=6)
        frame, self.mp_tree = make_tree(mr, [("title", "Modpack", 200), ("author", "Author", 110),
                                             ("downloads", "Downloads", 90), ("desc", "Description", 300)],
                                        selectmode="browse")
        frame.pack(fill="both", expand=True, pady=6)
        self.mp_hits: dict[str, modrinth.SearchHit] = {}
        self._packs_loaded = False
        self.nb.bind("<<NotebookTabChanged>>", self._tab_changed)

        ttk.Button(self.buttons, text="Cancel", command=self.close).pack(side="right")
        ttk.Button(self.buttons, text="Create", style="Accent.TButton", command=self.create).pack(side="right", padx=6)

    # -- helpers
    def _version_changed(self, v: str):
        self.loader.set_mc_version(v)
        self._update_auto_name()

    def _update_auto_name(self):
        v = self.versions.selected()
        loader = self.loader.loader.get()
        auto = v if loader == "vanilla" else f"{v} {loaders.LOADER_LABELS[loader]}"
        if not self.name.get() or self.name.get() == self._auto_name:
            self.name.set(auto)
        self._auto_name = auto

    def _browse_copy(self):
        d = filedialog.askdirectory(parent=self, title="Choose a .minecraft folder")
        if d:
            self.copy_from.set(d)

    def _browse_pack(self):
        f = filedialog.askopenfilename(parent=self, title="Choose modpack",
                                       filetypes=[("Modrinth modpack", "*.mrpack *.zip"), ("All files", "*")])
        if not f:
            return
        self.pack_path.set(f)
        try:
            idx = mrpack.read_index(Path(f))
            mc, loader, lv = mrpack.pack_info(idx)
            self.pack_info.configure(text=f"{idx.get('name', '')} {idx.get('versionId', '')}\n"
                                          f"Minecraft {mc} · {loaders.LOADER_LABELS[loader]} {lv}\n"
                                          f"{len(idx.get('files', []))} files to download")
            if not self.name.get() or self.name.get() == self._auto_name:
                self.name.set(idx.get("name", Path(f).stem))
                self._auto_name = self.name.get()
        except mrpack.PackError as e:
            self.pack_info.configure(text=str(e))

    def _tab_changed(self, _=None):
        if self.nb.index("current") == 2 and not self._packs_loaded:
            self._packs_loaded = True
            self._search_packs()

    def _search_packs(self):
        q = self.mp_query.get()

        def done(res):
            if not self.winfo_exists():
                return
            hits, _ = res
            self.mp_tree.delete(*self.mp_tree.get_children())
            self.mp_hits = {}
            for h in hits:
                self.mp_hits[h.project_id] = h
                self.mp_tree.insert("", "end", iid=h.project_id,
                                    values=(h.title, h.author, f"{h.downloads:,}", h.description))
        self.app.tasks.run(lambda p, c: modrinth.search(q, "modpack", sort="relevance" if q else "downloads"),
                           done, label="Searching Modrinth...", parent=self)

    # -- create
    def create(self):
        tab = self.nb.index("current")
        app = self.app
        name = self.name.get().strip()
        group = self.group.get().strip()
        if tab == 0:
            mc = self.versions.selected()
            if not mc:
                messagebox.showwarning("New instance", "Pick a Minecraft version.", parent=self)
                return
            loader, lv = self.loader.value()
            if loader != "vanilla" and not lv:
                messagebox.showwarning("New instance", f"No {loaders.LOADER_LABELS[loader]} version selected.",
                                       parent=self)
                return
            inst = app.instances.create(name or mc, mc, loader, lv, group)
            src = self.copy_from.get().strip()
            self.close()
            if src:
                app.tasks.run(lambda p, c: app.instances.import_minecraft_folder(Path(src), inst),
                              lambda _: self._after_create(inst), label="Copying files...")
            else:
                self._after_create(inst)
        elif tab == 1:
            path = self.pack_path.get().strip()
            if not path:
                messagebox.showwarning("Import", "Choose a .mrpack file first.", parent=self)
                return
            self.close()
            app.tasks.run(lambda p, c: mrpack.install_pack(Path(path), app.instances, name, p, c,
                                                           app.settings.download_workers),
                          lambda inst: self._after_pack(inst, group), label="Importing modpack...")
        else:
            sel = self.mp_tree.selection()
            if not sel:
                messagebox.showwarning("Modrinth", "Select a modpack first.", parent=self)
                return
            hit = self.mp_hits[sel[0]]
            self.close()

            def work(p, c):
                p(f"Finding latest version of {hit.title}...", None)
                vs = modrinth.project_versions(hit.project_id, project_type="modpack")
                if not vs:
                    raise ValueError("This modpack has no downloadable versions.")
                ver = next((v for v in vs if v.get("version_type") == "release"), vs[0])
                f = modrinth.primary_file(ver)
                dest = app.paths.cache / "modpacks" / Path(f["filename"]).name
                p(f"Downloading {f['filename']}...", None)
                net.download(f["url"], dest, sha1=(f.get("hashes") or {}).get("sha1"), cancel=c)
                return mrpack.install_pack(dest, app.instances, name if name != self._auto_name else hit.title,
                                           p, c, app.settings.download_workers)
            app.tasks.run(work, lambda inst: self._after_pack(inst, group), label=f"Installing {hit.title}...")

    def _after_pack(self, inst: Instance, group: str):
        if group:
            inst.group = group
            inst.save()
        self._after_create(inst)

    def _after_create(self, inst: Instance):
        app = self.app
        app.refresh_instances(inst.id)
        # Download game files right away so the first launch is quick.
        app.tasks.run(lambda p, c: launch.ensure_installed(app.paths, inst, p, c, app.settings.download_workers),
                      lambda _: app.refresh_instances(inst.id),
                      lambda e: messagebox.showwarning(
                          "Download incomplete", f"{inst.name} was created, but downloading game files failed:\n"
                          f"{e}\n\nThey will be downloaded again when you launch it.", parent=app.root),
                      label=f"Downloading {inst.mc_version}...")


# ====================================================================== settings

class SettingsDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Settings")
        s = app.settings
        nb = ttk.Notebook(self.body)
        nb.pack(fill="both", expand=True)

        gen = ttk.Frame(nb, padding=12)
        nb.add(gen, text="General")
        self.theme = tk.StringVar(value=s.theme)
        row = ttk.Frame(gen)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Theme:").pack(side="left")
        ttk.Combobox(row, textvariable=self.theme, values=["dark", "light"], state="readonly",
                     width=10).pack(side="left", padx=6)
        self.close_on_launch = tk.BooleanVar(value=s.close_on_launch)
        ttk.Checkbutton(gen, text="Hide the launcher while the game is running",
                        variable=self.close_on_launch).pack(anchor="w", pady=4)
        self.snapshots = tk.BooleanVar(value=s.show_snapshots)
        ttk.Checkbutton(gen, text="Show snapshots in version lists", variable=self.snapshots).pack(anchor="w", pady=4)
        row = ttk.Frame(gen)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Parallel downloads:").pack(side="left")
        self.workers = tk.IntVar(value=s.download_workers)
        ttk.Spinbox(row, from_=1, to=32, textvariable=self.workers, width=6).pack(side="left", padx=6)
        row = ttk.Frame(gen)
        row.pack(fill="x", pady=(14, 4))
        ttk.Label(row, text=f"Data folder: {app.paths.root}", style="Muted.TLabel").pack(side="left")
        ttk.Button(row, text="Open", command=lambda: open_path(app.paths.root)).pack(side="left", padx=6)

        jt = ttk.Frame(nb, padding=12)
        nb.add(jt, text="Java")
        self.java_path = tk.StringVar(value=s.java_path)
        ttk.Label(jt, text="Java executable (leave empty to choose the right version automatically):").pack(anchor="w")
        row = ttk.Frame(jt)
        row.pack(fill="x", pady=4)
        self.java_combo = ttk.Combobox(row, textvariable=self.java_path)
        self.java_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self._browse_java).pack(side="left", padx=4)
        ttk.Button(row, text="Detect", command=self._detect).pack(side="left")
        row = ttk.Frame(jt)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Download Java (Eclipse Temurin):").pack(side="left")
        self.dl_major = tk.StringVar(value="21")
        ttk.Combobox(row, textvariable=self.dl_major, values=["8", "17", "21", "25"], width=5,
                     state="readonly").pack(side="left", padx=6)
        ttk.Button(row, text="Download", command=self._download_java).pack(side="left")
        self.java_info = ttk.Label(jt, text="", style="Muted.TLabel", wraplength=560, justify="left")
        self.java_info.pack(anchor="w", pady=4)
        mem = ttk.LabelFrame(jt, text="Memory (MiB)", padding=8)
        mem.pack(fill="x", pady=8)
        self.min_mem = tk.IntVar(value=s.min_memory)
        self.max_mem = tk.IntVar(value=s.max_memory)
        ttk.Label(mem, text="Minimum:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(mem, from_=256, to=65536, increment=256, textvariable=self.min_mem, width=8).grid(row=0, column=1, padx=6)
        ttk.Label(mem, text="Maximum:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(mem, from_=512, to=65536, increment=256, textvariable=self.max_mem, width=8).grid(row=0, column=3, padx=6)
        ttk.Label(jt, text="Extra JVM arguments:").pack(anchor="w")
        self.jvm_args = tk.StringVar(value=s.jvm_args)
        ttk.Entry(jt, textvariable=self.jvm_args).pack(fill="x", pady=4)
        row = ttk.Frame(jt)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Game window size:").pack(side="left")
        self.w = tk.IntVar(value=s.window_width)
        self.h = tk.IntVar(value=s.window_height)
        ttk.Spinbox(row, from_=320, to=7680, textvariable=self.w, width=6).pack(side="left", padx=4)
        ttk.Label(row, text="x").pack(side="left")
        ttk.Spinbox(row, from_=240, to=4320, textvariable=self.h, width=6).pack(side="left", padx=4)

        ms = ttk.Frame(nb, padding=12)
        nb.add(ms, text="Microsoft login")
        ttk.Label(ms, wraplength=560, justify="left", text=(
            "Microsoft accounts need an Azure application (client) ID. Create one at "
            "portal.azure.com (App registrations > New registration, 'Personal Microsoft accounts', enable "
            "'Allow public client flows'). Mojang must approve new apps before they can log in to Minecraft.\n\n"
            "Without one you can still play with an offline account.")).pack(anchor="w")
        self.client_id = tk.StringVar(value=s.msa_client_id)
        row = ttk.Frame(ms)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text="Client ID:").pack(side="left")
        ttk.Entry(row, textvariable=self.client_id).pack(side="left", fill="x", expand=True, padx=6)

        ttk.Button(self.buttons, text="Cancel", command=self.close).pack(side="right")
        ttk.Button(self.buttons, text="Save", style="Accent.TButton", command=self.save).pack(side="right", padx=6)
        self._detect(quiet=True)

    def _browse_java(self):
        f = filedialog.askopenfilename(parent=self, title="Choose the java executable")
        if f:
            self.java_path.set(f)

    def _detect(self, quiet: bool = False):
        self.java_info.configure(text="Looking for Java installations...")

        def done(found):
            if not self.winfo_exists():
                return
            self.java_combo.configure(values=[j.path for j in found])
            if found:
                self.java_info.configure(text="Found:\n" + "\n".join(f"Java {j.version} ({j.arch})  {j.path}"
                                                                     for j in found[:8]))
            else:
                self.java_info.configure(text="No Java found. The launcher downloads the right one when you "
                                              "launch, or use Download above. " + java.linux_hint())
        self.app.tasks.run(lambda p, c: java.detect_all(self.app.paths), done, quiet=quiet,
                           label="Detecting Java...", parent=self)

    def _download_java(self):
        major = int(self.dl_major.get())

        def done(info):
            if self.winfo_exists():
                self.java_info.configure(text=f"Installed Java {info.version}: {info.path}")
                self._detect(quiet=True)
        self.app.tasks.run(lambda p, c: java.download_java(self.app.paths, major, p, c), done,
                           label=f"Downloading Java {major}...", parent=self)

    def save(self):
        s = self.app.settings
        try:
            min_mem, max_mem = int(self.min_mem.get()), int(self.max_mem.get())
            w, h, workers = int(self.w.get()), int(self.h.get()), int(self.workers.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Settings", "Memory, window size and downloads must be numbers.", parent=self)
            return
        if min_mem > max_mem:
            messagebox.showerror("Settings", "Minimum memory cannot be larger than maximum.", parent=self)
            return
        theme_changed = s.theme != self.theme.get()
        s.theme = self.theme.get()
        s.close_on_launch = self.close_on_launch.get()
        s.show_snapshots = self.snapshots.get()
        s.download_workers = max(1, min(32, workers))
        s.java_path = self.java_path.get().strip()
        s.min_memory, s.max_memory = min_mem, max_mem
        s.jvm_args = self.jvm_args.get().strip()
        s.window_width, s.window_height = w, h
        s.msa_client_id = self.client_id.get().strip()
        self.app.config.save()
        self.close()
        if theme_changed:
            self.app.apply_theme()


# ====================================================================== accounts

class AccountsDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Accounts")
        frame, self.tree = make_tree(self.body, [("name", "Name", 180), ("type", "Type", 100),
                                                 ("default", "Default", 70)], selectmode="browse")
        side = ttk.Frame(self.body, padding=(10, 0, 0, 0))
        side.pack(side="right", fill="y")
        frame.pack(side="left", fill="both", expand=True)
        ttk.Button(side, text="Add Microsoft", style="Accent.TButton", command=self.add_msa).pack(fill="x", pady=2)
        ttk.Button(side, text="Add Offline", command=self.add_offline).pack(fill="x", pady=2)
        ttk.Button(side, text="Set default", command=self.set_default).pack(fill="x", pady=(12, 2))
        ttk.Button(side, text="Remove", command=self.remove).pack(fill="x", pady=2)
        ttk.Button(side, text="Close", command=self.close).pack(side="bottom", fill="x")
        self.tree.bind("<Double-Button-1>", lambda e: self.set_default())
        self.fill()

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        d = self.app.accounts.default()
        for a in self.app.accounts.accounts:
            self.tree.insert("", "end", iid=a.uuid, values=(a.name, "Microsoft" if a.kind == "msa" else "Offline",
                                                            "yes" if d and d.uuid == a.uuid else ""))
        self.app._update_account_label()

    def _sel(self):
        s = self.tree.selection()
        return next((a for a in self.app.accounts.accounts if s and a.uuid == s[0]), None)

    def add_offline(self):
        name = simpledialog.askstring("Offline account", "Player name (3-16 letters, numbers or _):", parent=self)
        if not name:
            return
        try:
            self.app.accounts.add_offline(name.strip())
        except ValueError as e:
            messagebox.showerror("Offline account", str(e), parent=self)
        self.fill()

    def set_default(self):
        a = self._sel()
        if a:
            self.app.accounts.set_default(a)
            self.fill()

    def remove(self):
        a = self._sel()
        if a and messagebox.askyesno("Remove account", f"Remove {a.label}?", parent=self):
            self.app.accounts.remove(a)
            self.fill()

    def add_msa(self):
        client_id = self.app.settings.msa_client_id
        if not client_id:
            messagebox.showinfo("Microsoft login", "Set an Azure client ID first (Settings > Microsoft login).",
                                parent=self)
            return
        MicrosoftLoginDialog(self.app, self, client_id).show()


class MicrosoftLoginDialog(Dialog):
    def __init__(self, app, owner: AccountsDialog, client_id: str):
        super().__init__(app, "Microsoft login", parent=owner)
        self.owner = owner
        self.cancelled = threading.Event()
        self.msg = ttk.Label(self.body, text="Contacting Microsoft...", wraplength=420, justify="left")
        self.msg.pack(anchor="w")
        self.code = ttk.Label(self.body, text="", style="Title.TLabel")
        self.code.pack(pady=12)
        row = self.buttons
        self.open_btn = ttk.Button(row, text="Open login page", style="Accent.TButton", state="disabled")
        self.open_btn.pack(side="left")
        self.copy_btn = ttk.Button(row, text="Copy code", state="disabled")
        self.copy_btn.pack(side="left", padx=6)
        ttk.Button(row, text="Cancel", command=self.close).pack(side="right")

        def work(p, c):
            device = accounts.start_device_login(client_id)
            app.tasks.post(self._show_code, device)
            token = accounts.poll_device_login(client_id, device, self.cancelled.is_set)
            return accounts.complete_login(token)

        app.tasks.run(work, self._done, self._error, quiet=True)

    def _show_code(self, device):
        if not self.winfo_exists():
            return
        uri = device.get("verification_uri", "https://www.microsoft.com/link")
        code = device.get("user_code", "")
        self.msg.configure(text=f"Open {uri} in your browser and enter this code:")
        self.code.configure(text=code)

        def copy():
            self.clipboard_clear()
            self.clipboard_append(code)
        self.open_btn.configure(state="normal", command=lambda: webbrowser.open(uri))
        self.copy_btn.configure(state="normal", command=copy)

    def _done(self, acc):
        self.app.accounts.add(acc)
        if self.owner.winfo_exists():
            self.owner.fill()
        if self.winfo_exists():
            self.close()
        messagebox.showinfo("Microsoft login", f"Logged in as {acc.name}.", parent=self.app.root)

    def _error(self, e):
        if self.cancelled.is_set():
            return
        if self.winfo_exists():
            self.close()
        messagebox.showerror("Microsoft login", str(e), parent=self.app.root)

    def close(self):
        self.cancelled.set()
        super().close()


# ====================================================================== Modrinth browser

class ModrinthBrowser(Dialog):
    SORTS = {"Relevance": "relevance", "Downloads": "downloads", "Follows": "follows",
             "Newest": "newest", "Updated": "updated"}

    def __init__(self, app, inst: Instance, project_type: str = "mod", on_installed: Callable | None = None,
                 parent: tk.Misc | None = None):
        title = {"mod": "Download mods", "resourcepack": "Download resource packs",
                 "shader": "Download shader packs"}[project_type]
        super().__init__(app, f"{title} - {inst.name}", modal=False, parent=parent)
        self.geometry("900x600")
        self.inst = inst
        self.ptype = project_type
        self.on_installed = on_installed
        self.offset = 0
        self.total = 0
        self.hits: dict[str, modrinth.SearchHit] = {}

        top = ttk.Frame(self.body)
        top.pack(fill="x")
        self.query = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.query)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda ev: self.search(True))
        e.focus_set()
        self.sort = tk.StringVar(value="Relevance")
        ttk.Combobox(top, textvariable=self.sort, values=list(self.SORTS), state="readonly",
                     width=11).pack(side="left", padx=6)
        ttk.Button(top, text="Search", style="Accent.TButton", command=lambda: self.search(True)).pack(side="left")
        info = f"Showing results for Minecraft {inst.mc_version}"
        if project_type == "mod" and inst.loader != "vanilla":
            info += f" · {loaders.LOADER_LABELS[inst.loader]}"
        ttk.Label(self.body, text=info, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        bottom = ttk.Frame(self.buttons)
        bottom.pack(fill="x")
        self.status = ttk.Label(bottom, text="", style="Muted.TLabel")
        self.status.pack(side="left")
        ttk.Button(bottom, text="Close", command=self.close).pack(side="right")
        ttk.Button(bottom, text="Install selected", style="Accent.TButton", command=self.install).pack(side="right", padx=6)
        self.more_btn = ttk.Button(bottom, text="More results", command=lambda: self.search(False))
        self.more_btn.pack(side="right")

        pane = ttk.PanedWindow(self.body, orient="horizontal")
        pane.pack(fill="both", expand=True, pady=6)
        frame, self.tree = make_tree(pane, [("title", "Name", 220), ("author", "Author", 110),
                                            ("downloads", "Downloads", 90)])
        pane.add(frame, weight=3)
        detail = ttk.Frame(pane, padding=(10, 0, 0, 0))
        pane.add(detail, weight=2)
        self.d_title = ttk.Label(detail, text="", style="Heading.TLabel", wraplength=300, justify="left")
        self.d_title.pack(anchor="w")
        self.d_desc = ttk.Label(detail, text="Select a project to see details.", wraplength=300, justify="left")
        self.d_desc.pack(anchor="w", pady=6)
        self.d_link = ttk.Button(detail, text="Open on Modrinth", state="disabled")
        self.d_link.pack(anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self._show)
        self.tree.bind("<Double-Button-1>", lambda e: self.install())
        self.search(True)

    def search(self, new: bool):
        if new:
            self.offset = 0
        q, sort = self.query.get(), self.SORTS[self.sort.get()]
        inst = self.inst
        offset = self.offset

        def done(res):
            if not self.winfo_exists():
                return
            hits, total = res
            if new:
                self.tree.delete(*self.tree.get_children())
                self.hits = {}
            for h in hits:
                if h.project_id in self.hits:
                    continue
                self.hits[h.project_id] = h
                self.tree.insert("", "end", iid=h.project_id, values=(h.title, h.author, f"{h.downloads:,}"))
            self.total = total
            self.offset = offset + len(hits)
            self.status.configure(text=f"{len(self.hits)} of {total} results")
            self.more_btn.configure(state="normal" if self.offset < total else "disabled")

        self.app.tasks.run(lambda p, c: modrinth.search(q, self.ptype, inst.mc_version, inst.loader,
                                                        offset=offset, sort=sort),
                           done, label="Searching Modrinth...", parent=self)

    def _show(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        h = self.hits[sel[0]]
        self.d_title.configure(text=h.title)
        self.d_desc.configure(text=f"by {h.author}\n\n{h.description}\n\n" + ", ".join(h.categories))
        self.d_link.configure(state="normal", command=lambda: webbrowser.open(h.url))

    def install(self):
        sel = [self.hits[i] for i in self.tree.selection()]
        if not sel:
            return
        inst = self.inst

        def work(p, c):
            names = []
            for h in sel:
                if c.is_set():
                    raise net.Cancelled()
                p(f"Installing {h.title}...", None)
                names += modrinth.install(h.project_id, inst.game_dir, inst.mc_version, inst.loader,
                                          self.ptype, progress=p)
            return names

        def done(names):
            if self.on_installed:
                self.on_installed()
            msg = ("Installed:\n" + "\n".join(names)) if names else "Already installed."
            messagebox.showinfo("Modrinth", msg, parent=self if self.winfo_exists() else self.app.root)

        self.app.tasks.run(work, done, label="Installing from Modrinth...", parent=self)


def describe_size(path: Path) -> str:
    try:
        if path.is_dir():
            return ""
        return human_size(path.stat().st_size)
    except OSError:
        return ""
