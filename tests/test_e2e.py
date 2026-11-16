"""End-to-end test: install + launch through a fake Mojang/Fabric/Modrinth server.

Needs a JDK (javac + java) on PATH; skipped otherwise.
"""
import hashlib
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vanquish import accounts, java, launch, loaders, modrinth, versions  # noqa: E402
from vanquish.config import Config, Paths  # noqa: E402
from vanquish.instances import InstanceManager  # noqa: E402
from vanquish.platform_utils import mojang_os_name  # noqa: E402

MAIN_JAVA = """
import java.io.File;
public class Main {
  public static void main(String[] a) throws Exception {
    System.out.println("ARGS:" + String.join(" ", a));
    System.out.println("LIB:" + Lib.hello());
    File dir = new File(System.getProperty("java.library.path"));
    System.out.println("NATIVE:" + new File(dir, "libfake.so").exists());
    System.out.println("EMU:" + System.getProperty("FabricMcEmu"));
  }
}
"""
LIB_JAVA = "public class Lib { public static String hello() { return \"hi\"; } }"
FMAIN_JAVA = "public class FabricMain { public static void main(String[] a) throws Exception { " \
             "System.out.println(\"FABRIC\"); Main.main(a); } }"


def sha1(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "JDK not installed")
class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        www = root / "www"
        build = root / "build"
        build.mkdir()
        for name, src in (("Main", MAIN_JAVA), ("Lib", LIB_JAVA), ("FabricMain", FMAIN_JAVA)):
            (build / f"{name}.java").write_text(src)
        subprocess.run(["javac", "-d", str(build), *map(str, build.glob("*.java"))], check=True,
                       capture_output=True)

        def jar(path: Path, entries: dict):
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path, "w") as zf:
                for k, v in entries.items():
                    zf.writestr(k, v)
            return path

        handler_dir = str(www)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=handler_dir, **k)

            def log_message(self, *a):
                pass

            def do_POST(self):  # Modrinth update check
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                result = {}
                for h in body["hashes"]:
                    if h == cls.old_mod_sha:
                        result[h] = json.loads((www / "mr" / "version" / "v2").read_text())
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def translate_path(self, path):
                # map query strings to files: /mr/search?x -> /mr/search
                fs = super().translate_path(path.split("?", 1)[0])
                if Path(fs).is_dir() and (Path(fs) / "_").is_file():
                    return str(Path(fs) / "_")  # a URL that is both a file and a folder
                return fs

        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = cls.server.server_address[1]
        base = f"http://127.0.0.1:{port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

        client = jar(www / "client.jar", {"Main.class": (build / "Main.class").read_bytes()})
        lib = jar(www / "lib.jar", {"Lib.class": (build / "Lib.class").read_bytes()})
        natives = jar(www / "natives.jar", {"libfake.so": b"x", "META-INF/MANIFEST.MF": "x"})
        jar(www / "maven" / "net" / "fake" / "fabricmain" / "1.0" / "fabricmain-1.0.jar",
            {"FabricMain.class": (build / "FabricMain.class").read_bytes()})
        asset = www / "res" / "ab" / "ab"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"asset")
        asset_sha = sha1(asset)
        (www / "res" / asset_sha[:2]).mkdir(exist_ok=True)
        shutil.copy(asset, www / "res" / asset_sha[:2] / asset_sha)
        index = www / "index.json"
        index.write_text(json.dumps({"objects": {"icons/a.png": {"hash": asset_sha, "size": 5}}}))
        major = java.probe(shutil.which("java")).major
        osname = mojang_os_name()
        version = {
            "id": "1.0-test", "type": "release", "mainClass": "Main",
            "assetIndex": {"id": "t", "url": f"{base}/index.json", "sha1": sha1(index)},
            "assets": "t", "javaVersion": {"majorVersion": major},
            "downloads": {"client": {"url": f"{base}/client.jar", "sha1": sha1(client),
                                     "size": client.stat().st_size}},
            "libraries": [
                {"name": "fake:lib:1", "downloads": {"artifact": {
                    "path": "fake/lib/1/lib-1.jar", "url": f"{base}/lib.jar", "sha1": sha1(lib),
                    "size": lib.stat().st_size}}},
                {"name": "fake:never:1", "rules": [{"action": "allow", "os": {"name": "nonexistent"}}],
                 "downloads": {"artifact": {"path": "fake/never.jar", "url": f"{base}/missing.jar"}}},
                {"name": "fake:nat:1", "natives": {osname: "natives-x"}, "extract": {"exclude": ["META-INF/"]},
                 "downloads": {"classifiers": {"natives-x": {
                     "path": "fake/nat/1/nat-1-natives.jar", "url": f"{base}/natives.jar",
                     "sha1": sha1(natives), "size": natives.stat().st_size}}}},
            ],
            "arguments": {
                "game": ["--username", "${auth_player_name}", "--uuid", "${auth_uuid}",
                         "--gameDir", "${game_directory}",
                         {"rules": [{"action": "allow", "features": {"has_custom_resolution": True}}],
                          "value": ["--width", "${resolution_width}"]},
                         {"rules": [{"action": "allow", "features": {"is_demo_user": True}}], "value": "--demo"}],
                "jvm": ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"]},
        }
        vfile = www / "1.0-test.json"
        vfile.write_text(json.dumps(version))
        (www / "manifest.json").write_text(json.dumps({
            "latest": {"release": "1.0-test"},
            "versions": [{"id": "1.0-test", "type": "release", "url": f"{base}/1.0-test.json",
                          "sha1": sha1(vfile), "releaseTime": "2024-01-01"}]}))
        fab = www / "fabric" / "versions" / "loader" / "1.0-test"
        fab.mkdir(parents=True)
        (fab / "_").write_text(
            json.dumps([{"loader": {"version": "0.1.0", "stable": True}}]))
        (fab / "0.1.0" / "profile").mkdir(parents=True)
        (fab / "0.1.0" / "profile" / "json").write_text(json.dumps({
            "id": "fabric-loader-0.1.0-1.0-test", "inheritsFrom": "1.0-test", "mainClass": "FabricMain",
            "libraries": [{"name": "net.fake:fabricmain:1.0", "url": f"{base}/maven/"}],
            "arguments": {"game": [], "jvm": ["-DFabricMcEmu= Main"]}}))

        # Modrinth fixtures
        mr = www / "mr"
        mod_old = jar(www / "files" / "coolmod-1.jar", {"fabric.mod.json": '{"id":"cool","version":"1"}'})
        mod_new = jar(www / "files" / "coolmod-2.jar", {"fabric.mod.json": '{"id":"cool","version":"2"}'})
        dep = jar(www / "files" / "api.jar", {"fabric.mod.json": '{"id":"api","version":"1"}'})
        cls.old_mod_sha = sha1(mod_old)

        def ver(vid, pid, f, deps=()):
            return {"id": vid, "project_id": pid, "version_number": vid, "version_type": "release",
                    "files": [{"url": f"{base}/files/{f.name}", "filename": f.name, "primary": True,
                               "hashes": {"sha1": sha1(f)}}],
                    "dependencies": [{"project_id": d, "dependency_type": "required"} for d in deps]}
        (mr / "project" / "cool").mkdir(parents=True)
        (mr / "project" / "api").mkdir(parents=True)
        (mr / "version").mkdir(parents=True)
        (mr / "project" / "cool" / "version").write_text(json.dumps([ver("v1", "cool", mod_old, ["api"])]))
        (mr / "project" / "api" / "version").write_text(json.dumps([ver("a1", "api", dep)]))
        (mr / "version" / "v2").write_text(json.dumps(ver("v2", "cool", mod_new)))
        (mr / "search").write_text(json.dumps({"hits": [{"project_id": "cool", "slug": "cool", "title": "Cool",
                                                         "author": "me", "description": "d", "downloads": 5,
                                                         "project_type": "mod"}], "total_hits": 1}))

        cls.patches = [
            mock.patch.object(versions, "MANIFEST_URL", f"{base}/manifest.json"),
            mock.patch.object(versions, "RESOURCES_URL", f"{base}/res/"),
            mock.patch.dict(loaders.LOADERS["fabric"], {"meta": f"{base}/fabric"}),
            mock.patch.object(modrinth, "API", f"{base}/mr"),
        ]
        for p in cls.patches:
            p.start()
        cls.paths = Paths(root / "data").ensure()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        cls.server.shutdown()
        cls.tmp.cleanup()

    def _run(self, inst):
        cfg = Config(self.paths)
        acc = accounts.Account("offline", "Steve", accounts.offline_uuid("Steve"))
        cmd = launch.prepare(self.paths, inst, acc, cfg.settings)
        lines, done = [], threading.Event()
        codes = []
        launch.start(cmd, inst.game_dir, lines.append, lambda c: (codes.append(c), done.set()))
        self.assertTrue(done.wait(60))
        return cmd, "\n".join(lines), codes[0]

    def test_vanilla_launch(self):
        inst = InstanceManager(self.paths).create("Vanilla", "1.0-test")
        cmd, out, code = self._run(inst)
        self.assertEqual(code, 0, out)
        self.assertIn("ARGS:--username Steve --uuid " + accounts.offline_uuid("Steve").replace("-", ""), out)
        self.assertIn("--width 854", out)
        self.assertNotIn("--demo", out)
        self.assertIn("LIB:hi", out)
        self.assertIn("NATIVE:true", out)
        self.assertTrue((self.paths.assets / "objects").exists())
        self.assertFalse(any("never" in c for c in cmd))

    def test_fabric_launch(self):
        inst = InstanceManager(self.paths).create("Fab", "1.0-test", "fabric", "")
        cmd, out, code = self._run(inst)
        self.assertEqual(code, 0, out)
        self.assertIn("FABRIC", out)
        self.assertIn("EMU: Main", out)
        self.assertEqual(inst.loader_version, "0.1.0")
        self.assertEqual(inst.version_id, "fabric-loader-0.1.0-1.0-test")

    def test_modrinth_install_and_update(self):
        inst = InstanceManager(self.paths).create("MR", "1.0-test", "fabric", "0.1.0")
        hits, total = modrinth.search("cool", "mod", "1.0-test", "fabric")
        self.assertEqual((hits[0].project_id, total), ("cool", 1))
        names = modrinth.install("cool", inst.game_dir, "1.0-test", "fabric")
        self.assertEqual(sorted(names), ["api.jar", "coolmod-1.jar"])
        self.assertEqual(modrinth.install("cool", inst.game_dir, "1.0-test", "fabric"), [])
        updates = modrinth.check_updates(sorted(inst.mods_dir.glob("*.jar")), "1.0-test", "fabric")
        self.assertEqual([p.name for p in updates], ["coolmod-1.jar"])
        (path, v), = updates.items()
        new = modrinth.apply_update(path, v)
        self.assertEqual(new.name, "coolmod-2.jar")
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
