import requests
import json
import shutil
import hashlib
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

class ModrinthAPI:
    def __init__(self, cache_dir):
        self.base_url = "https://api.modrinth.com/v2"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "VanquishMM/V2"})
        self.cache_dir = cache_dir

    def search_mods(self, query, loaders=None, versions=None, limit=20):
        facets = [["project_type:mod"]]
        if loaders:
            facets.append([f"categories:{l}" for l in loaders])
        if versions:
            facets.append([f"versions:{v}" for v in versions])
        params = {"query": query, "limit": limit, "facets": json.dumps(facets)}
        try:
            r = self.session.get(f"{self.base_url}/search", params=params)
            r.raise_for_status()
            return r.json().get("hits", [])
        except:
            return []

    def get_version_by_hash(self, file_hash):
        try:
            r = self.session.get(f"{self.base_url}/version_file/{file_hash}")
            if r.status_code == 200:
                return r.json()
        except:
            pass
        return None

    def get_versions(self, slug, loaders=None, game_versions=None):
        params = {}
        if loaders: params["loaders"] = json.dumps(loaders)
        if game_versions: params["game_versions"] = json.dumps(game_versions)
        try:
            r = self.session.get(f"{self.base_url}/project/{slug}/version", params=params)
            return r.json() if r.status_code == 200 else []
        except:
            return []

class ModManager:
    def __init__(self, config):
        self.config = config
        self.api = ModrinthAPI(config.cache_dir)
        self.mc_path = Path(config.get("minecraft_path"))
        self.mods_path = self.mc_path / "mods"
        self.mods_path.mkdir(exist_ok=True, parents=True)
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _calculate_sha1(self, file_path):
        sha1 = hashlib.sha1()
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data: break
                sha1.update(data)
        return sha1.hexdigest()

    def get_installed_mods(self):
        mods = []
        if not self.mods_path.exists(): return mods
        for f in self.mods_path.glob("*.jar"):
            mods.append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "enabled": not f.name.endswith(".disabled")
            })
        return mods

    def check_for_updates(self, progress_callback=None):
        updates = []
        mods = self.get_installed_mods()
        total = len(mods)
        for i, mod in enumerate(mods):
            if not mod['enabled']: continue
            if progress_callback: progress_callback(i / total, f"Checking {mod['name']}...")
            file_hash = self._calculate_sha1(mod['path'])
            version_data = self.api.get_version_by_hash(file_hash)
            if version_data:
                project_id = version_data['project_id']
                latest_versions = self.api.get_versions(project_id)
                if latest_versions:
                    latest = latest_versions[0]
                    if latest['id'] != version_data['id']:
                        updates.append({
                            "mod": mod,
                            "current_ver": version_data['version_number'],
                            "new_ver": latest['version_number'],
                            "new_file": latest['files'][0]
                        })
        if progress_callback: progress_callback(1.0, "Done")
        return updates

    def create_backup(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = self.config.backups_dir / f"mods_backup_{timestamp}"
        try:
            shutil.make_archive(str(backup_name), 'zip', self.mods_path)
            return str(backup_name) + ".zip"
        except Exception as e:
            return None

    def toggle_mod(self, file_path):
        p = Path(file_path)
        if not p.exists(): return False
        new_name = p.name[:-9] if p.name.endswith(".disabled") else p.name + ".disabled"
        try:
            p.rename(p.parent / new_name)
            return True
        except:
            return False

    def delete_mod(self, file_path):
        try:
            Path(file_path).unlink()
            return True
        except:
            return False

    def download_mod(self, url, filename, callback=None):
        def _download():
            try:
                r = requests.get(url, stream=True)
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                dest = self.mods_path / filename
                downloaded = 0
                with open(dest, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback and total > 0: callback(downloaded / total)
                if callback: callback(1.0)
                return True
            except Exception as e:
                print(e)
                if callback: callback(-1)
                return False
        self.executor.submit(_download)

    def get_skin_url(self, username):
        return f"https://mc-heads.net/body/{quote(username)}/right"