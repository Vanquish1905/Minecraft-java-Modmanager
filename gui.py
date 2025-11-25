import customtkinter as ctk
import threading
import os
import webbrowser
from tkinter import filedialog, messagebox
from PIL import Image
from io import BytesIO
import requests

class App(ctk.CTk):
    def __init__(self, config, manager):
        super().__init__()
        self.config = config
        self.manager = manager
        ctk.set_appearance_mode(config.get("appearance_mode"))
        ctk.set_default_color_theme(config.get("color_theme"))
        ctk.set_widget_scaling(config.get("ui_scale"))
        self.title(config.app_name)
        self.geometry("1100x750")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._setup_ui()

    def _setup_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)
        self.logo = ctk.CTkLabel(self.sidebar, text="VANQUISH\nMOD MANAGER", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.btn_dash = self._nav_btn("Dashboard", self.show_dashboard, 1)
        self.btn_search = self._nav_btn("Browse Mods", self.show_search, 2)
        self.btn_mods = self._nav_btn("Installed Mods", self.show_installed, 3)
        self.btn_backups = self._nav_btn("Backups", self.show_backups, 4)
        self.btn_settings = self._nav_btn("Settings", self.show_settings, 5)
        self.version_lbl = ctk.CTkLabel(self.sidebar, text=f"v{self.config.version}", text_color="gray50")
        self.version_lbl.grid(row=7, column=0, pady=10)
        self.main_area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.show_dashboard()

    def _nav_btn(self, text, cmd, row):
        btn = ctk.CTkButton(self.sidebar, text=text, command=cmd, fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", height=40)
        btn.grid(row=row, column=0, padx=10, pady=5, sticky="ew")
        return btn

    def clear_main(self):
        for widget in self.main_area.winfo_children(): widget.destroy()

    def show_dashboard(self):
        self.clear_main()
        self.main_area.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.main_area, text="Dashboard", font=("Arial", 28, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 20))
        stats_frame = ctk.CTkFrame(self.main_area)
        stats_frame.grid(row=1, column=0, sticky="ew")
        mods = self.manager.get_installed_mods()
        enabled = sum(1 for m in mods if m['enabled'])
        total_size = sum(m['size'] for m in mods) / (1024*1024)
        self._stat_card(stats_frame, "Total Mods", str(len(mods)), 0)
        self._stat_card(stats_frame, "Active", str(enabled), 1)
        self._stat_card(stats_frame, "Size", f"{total_size:.1f} MB", 2)
        action_frame = ctk.CTkFrame(self.main_area)
        action_frame.grid(row=2, column=0, sticky="ew", pady=20)
        ctk.CTkLabel(action_frame, text="Quick Actions", font=("Arial", 16, "bold")).pack(anchor="w", padx=15, pady=10)
        btn_box = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_box, text="Check Updates", command=self.run_updater, fg_color="orange").pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="Open Folder", command=self.open_folder).pack(side="left", padx=5)
        skin_frame = ctk.CTkFrame(self.main_area)
        skin_frame.grid(row=3, column=0, sticky="nsew", pady=10)
        ctk.CTkLabel(skin_frame, text="Skin Preview", font=("Arial", 16, "bold")).pack(anchor="w", padx=15, pady=10)
        input_box = ctk.CTkFrame(skin_frame, fg_color="transparent")
        input_box.pack(fill="x", padx=10)
        self.skin_entry = ctk.CTkEntry(input_box, placeholder_text="Username", width=200)
        self.skin_entry.pack(side="left", padx=5)
        ctk.CTkButton(input_box, text="Load", width=80, command=self.load_skin).pack(side="left")
        self.skin_label = ctk.CTkLabel(skin_frame, text="")
        self.skin_label.pack(pady=10)

    def _stat_card(self, parent, title, value, col):
        f = ctk.CTkFrame(parent, fg_color=("gray85", "gray20"))
        f.grid(row=0, column=col, padx=10, pady=10, sticky="ew")
        parent.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(f, text=value, font=("Arial", 30, "bold")).pack(pady=(15,0))
        ctk.CTkLabel(f, text=title, text_color="gray50").pack(pady=(0,15))

    def load_skin(self):
        user = self.skin_entry.get()
        if not user: return
        def _fetch():
            try:
                url = self.manager.get_skin_url(user)
                resp = requests.get(url, stream=True)
                img = Image.open(BytesIO(resp.content)).resize((120, 260))
                ctk_img = ctk.CTkImage(img, size=(120, 260))
                self.skin_label.configure(image=ctk_img, text="")
            except: pass
        threading.Thread(target=_fetch).start()

    def open_folder(self):
        os.startfile(self.config.get("minecraft_path"))

    def run_updater(self):
        top = ctk.CTkToplevel(self)
        top.title("Mod Updater")
        top.geometry("400x200")
        lbl = ctk.CTkLabel(top, text="Checking...", font=("Arial", 16))
        lbl.pack(pady=20)
        bar = ctk.CTkProgressBar(top)
        bar.pack(pady=10, padx=20, fill="x")
        bar.set(0)
        def _update_progress(val, msg):
            bar.set(val)
            lbl.configure(text=msg)
        def _worker():
            updates = self.manager.check_for_updates(_update_progress)
            top.destroy()
            if updates: self.show_update_results(updates)
            else: messagebox.showinfo("Updater", "All mods are up to date!")
        threading.Thread(target=_worker).start()

    def show_update_results(self, updates):
        msg = f"Found {len(updates)} updates:\n\n"
        for u in updates[:10]: msg += f"{u['mod']['name']} -> {u['new_ver']}\n"
        if len(updates) > 10: msg += "...and more."
        if messagebox.askyesno("Updates Found", msg + "\nUpdate now?"):
            for u in updates:
                self.manager.download_mod(u['new_file']['url'], u['new_file']['filename'])
                self.manager.delete_mod(u['mod']['path'])
            messagebox.showinfo("Done", "Updates installed.")
            self.show_installed()

    def show_installed(self):
        self.clear_main()
        ctk.CTkLabel(self.main_area, text="Installed Mods", font=("Arial", 28, "bold")).pack(anchor="w", pady=(0, 20))
        scroll = ctk.CTkScrollableFrame(self.main_area)
        scroll.pack(fill="both", expand=True)
        for mod in self.manager.get_installed_mods():
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=2)
            status = "ENABLED" if mod['enabled'] else "DISABLED"
            color = "green" if mod['enabled'] else "gray"
            ctk.CTkLabel(row, text=mod['name'], font=("Arial", 14)).pack(side="left", padx=10, pady=10)
            ctk.CTkLabel(row, text=f"{mod['size']/1024:.0f} KB", text_color="gray").pack(side="left", padx=10)
            ctk.CTkButton(row, text="Delete", width=60, fg_color="#ef4444", hover_color="#b91c1c", command=lambda m=mod['path']: self._delete_mod(m)).pack(side="right", padx=5)
            ctk.CTkButton(row, text=status, width=80, fg_color=color, command=lambda m=mod['path']: self._toggle_mod(m)).pack(side="right", padx=5)

    def _toggle_mod(self, path):
        self.manager.toggle_mod(path)
        self.show_installed()

    def _delete_mod(self, path):
        if messagebox.askyesno("Confirm", "Delete this mod?"):
            self.manager.delete_mod(path)
            self.show_installed()

    def show_backups(self):
        self.clear_main()
        ctk.CTkLabel(self.main_area, text="Backups", font=("Arial", 28, "bold")).pack(anchor="w", pady=(0, 20))
        ctk.CTkButton(self.main_area, text="+ Create New Backup", command=self._create_backup).pack(anchor="w", pady=10)
        scroll = ctk.CTkScrollableFrame(self.main_area)
        scroll.pack(fill="both", expand=True, pady=10)
        backups = list(self.config.backups_dir.glob("*.zip"))
        backups.sort(key=os.path.getmtime, reverse=True)
        for b in backups:
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=b.name).pack(side="left", padx=10, pady=10)
            ctk.CTkLabel(row, text=f"{b.stat().st_size / (1024*1024):.2f} MB", text_color="gray").pack(side="left", padx=10)
            ctk.CTkButton(row, text="Open Location", command=lambda p=b: os.startfile(p.parent)).pack(side="right", padx=10)

    def _create_backup(self):
        res = self.manager.create_backup()
        if res:
            messagebox.showinfo("Success", f"Backup created:\n{os.path.basename(res)}")
            self.show_backups()
        else: messagebox.showerror("Error", "Failed to create backup.")

    def show_search(self):
        self.clear_main()
        ctk.CTkLabel(self.main_area, text="Browse Modrinth", font=("Arial", 28, "bold")).pack(anchor="w", pady=(0, 20))
        filters = ctk.CTkFrame(self.main_area)
        filters.pack(fill="x", pady=(0, 10))
        self.search_entry = ctk.CTkEntry(filters, placeholder_text="Search...")
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.ver_box = ctk.CTkComboBox(filters, values=["1.20.1", "1.20.4", "1.19.2", "1.18.2"])
        self.ver_box.pack(side="left", padx=5)
        self.loader_box = ctk.CTkComboBox(filters, values=["fabric", "forge", "quilt"])
        self.loader_box.pack(side="left", padx=5)
        ctk.CTkButton(filters, text="Search", command=self._do_search).pack(side="left", padx=5)
        self.results_frame = ctk.CTkScrollableFrame(self.main_area)
        self.results_frame.pack(fill="both", expand=True)

    def _do_search(self):
        for w in self.results_frame.winfo_children(): w.destroy()
        q, v, l = self.search_entry.get(), self.ver_box.get(), self.loader_box.get()
        def _thread():
            results = self.manager.api.search_mods(q, [l], [v])
            self.after(0, lambda: self._show_results(results, v, l))
        threading.Thread(target=_thread).start()

    def _show_results(self, results, v, l):
        for r in results:
            f = ctk.CTkFrame(self.results_frame)
            f.pack(fill="x", pady=5)
            ctk.CTkLabel(f, text=r['title'], font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=(5,0))
            ctk.CTkLabel(f, text=r['description'], text_color="gray70").pack(anchor="w", padx=10, pady=(0,5))
            ctk.CTkButton(f, text="Install", width=80, command=lambda x=r: self._install_mod(x, v, l)).pack(anchor="e", padx=10, pady=5)

    def _install_mod(self, mod, v, l):
        def _worker():
            vers = self.manager.api.get_versions(mod['slug'], [l], [v])
            if vers:
                f = vers[0]['files'][0]
                self.manager.download_mod(f['url'], f['filename'])
                self.after(0, lambda: messagebox.showinfo("Installed", f"Installed {mod['title']}"))
            else: self.after(0, lambda: messagebox.showerror("Error", "No compatible version found."))
        threading.Thread(target=_worker).start()

    def show_settings(self):
        self.clear_main()
        ctk.CTkLabel(self.main_area, text="Settings", font=("Arial", 28, "bold")).pack(anchor="w", pady=(0, 20))
        f = ctk.CTkFrame(self.main_area); f.pack(fill="x", pady=5)
        ctk.CTkLabel(f, text="Minecraft Path").pack(side="left", padx=20, pady=20)
        self.path_ent = ctk.CTkEntry(f, width=400); self.path_ent.pack(side="left", padx=10)
        self.path_ent.insert(0, self.config.get("minecraft_path"))
        f2 = ctk.CTkFrame(self.main_area); f2.pack(fill="x", pady=5)
        ctk.CTkLabel(f2, text="Appearance Mode").pack(side="left", padx=20, pady=20)
        self.app_mode = ctk.CTkComboBox(f2, values=["Dark", "Light", "System"])
        self.app_mode.pack(side="left", padx=10); self.app_mode.set(self.config.get("appearance_mode"))
        f3 = ctk.CTkFrame(self.main_area); f3.pack(fill="x", pady=5)
        ctk.CTkLabel(f3, text="Color Theme").pack(side="left", padx=20, pady=20)
        self.color_theme = ctk.CTkComboBox(f3, values=["blue", "green", "dark-blue"])
        self.color_theme.pack(side="left", padx=10); self.color_theme.set(self.config.get("color_theme"))
        f4 = ctk.CTkFrame(self.main_area); f4.pack(fill="x", pady=5)
        ctk.CTkLabel(f4, text="UI Scale").pack(side="left", padx=20, pady=20)
        self.scale_slider = ctk.CTkSlider(f4, from_=0.7, to=1.5, number_of_steps=8)
        self.scale_slider.pack(side="left", padx=10, fill="x", expand=True); self.scale_slider.set(self.config.get("ui_scale"))
        ctk.CTkButton(self.main_area, text="Save & Apply", command=self._save_settings, height=50).pack(fill="x", pady=20)

    def _save_settings(self):
        self.config.set("minecraft_path", self.path_ent.get())
        self.config.set("appearance_mode", self.app_mode.get())
        self.config.set("color_theme", self.color_theme.get())
        self.config.set("ui_scale", self.scale_slider.get())
        ctk.set_appearance_mode(self.app_mode.get())
        ctk.set_default_color_theme(self.color_theme.get())
        ctk.set_widget_scaling(self.scale_slider.get())
        messagebox.showinfo("Saved", "Settings saved!")