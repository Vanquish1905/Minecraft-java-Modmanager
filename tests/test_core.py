import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vanquish import accounts, mods, mrpack, versions  # noqa: E402
from vanquish.config import Config, Paths  # noqa: E402
from vanquish.instances import InstanceManager  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_no_rules_allows(self):
        self.assertTrue(versions.rules_allow(None))

    def test_os_rules(self):
        with mock.patch.object(versions, "mojang_os_name", return_value="linux"):
            self.assertTrue(versions.rules_allow([{"action": "allow"},
                                                  {"action": "disallow", "os": {"name": "osx"}}]))
            self.assertFalse(versions.rules_allow([{"action": "allow", "os": {"name": "osx"}}]))
            self.assertTrue(versions.rules_allow([{"action": "allow", "os": {"name": "linux"}}]))

    def test_mac_arm_suffix(self):
        with mock.patch.object(versions, "mojang_os_name", return_value="osx"), \
                mock.patch.object(versions, "machine_arch", return_value="arm64"):
            self.assertTrue(versions.rules_allow([{"action": "allow", "os": {"name": "osx-arm64"}}]))
            self.assertFalse(versions.rules_allow([{"action": "allow", "os": {"name": "osx", "arch": "x86"}}]))

    def test_features(self):
        rule = [{"action": "allow", "features": {"is_demo_user": True}}]
        self.assertFalse(versions.rules_allow(rule, {}))
        self.assertTrue(versions.rules_allow(rule, {"is_demo_user": True}))


class MavenTest(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(versions.maven_path("net.fabricmc:fabric-loader:0.15.0"),
                         "net/fabricmc/fabric-loader/0.15.0/fabric-loader-0.15.0.jar")
        self.assertEqual(versions.maven_path("org.lwjgl:lwjgl:3.3.1:natives-linux"),
                         "org/lwjgl/lwjgl/3.3.1/lwjgl-3.3.1-natives-linux.jar")
        self.assertEqual(versions.maven_path("a.b:c:1@zip"), "a/b/c/1/c-1.zip")

    def test_merge_child_wins(self):
        parent = {"id": "1.20.1", "mainClass": "net.minecraft.client.main.Main",
                  "libraries": [{"name": "org.ow2.asm:asm:9.1"}, {"name": "x:y:1"},
                                {"name": "x:y:1", "rules": [{"action": "allow", "os": {"name": "osx"}}]}],
                  "arguments": {"game": ["--a"], "jvm": ["-cp", "${classpath}"]}}
        child = {"id": "fabric", "inheritsFrom": "1.20.1", "mainClass": "net.fabricmc.Knot",
                 "libraries": [{"name": "org.ow2.asm:asm:9.6"}], "arguments": {"jvm": ["-Dx=1"]}}
        m = versions.merge_versions(child, parent)
        self.assertEqual(m["mainClass"], "net.fabricmc.Knot")
        self.assertEqual(m["jar"], "1.20.1")
        self.assertEqual([lib["name"] for lib in m["libraries"]], ["org.ow2.asm:asm:9.6", "x:y:1", "x:y:1"])
        self.assertEqual(m["arguments"]["jvm"], ["-cp", "${classpath}", "-Dx=1"])
        self.assertEqual(m["arguments"]["game"], ["--a"])


class AccountsTest(unittest.TestCase):
    def test_offline_uuid_matches_java(self):
        # UUID.nameUUIDFromBytes("OfflinePlayer:Notch".getBytes(UTF_8))
        self.assertEqual(accounts.offline_uuid("Notch"), "b50ad385-829d-3141-a216-7e7d7539ba7f")

    def test_store(self):
        with tempfile.TemporaryDirectory() as d:
            paths = Paths(Path(d)).ensure()
            store = accounts.AccountStore(paths)
            with self.assertRaises(ValueError):
                store.add_offline("a b")
            a = store.add_offline("Steve")
            self.assertEqual(accounts.AccountStore(paths).default().uuid, a.uuid)
            store.remove(a)
            self.assertIsNone(accounts.AccountStore(paths).default())


def make_jar(path: Path, files: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


class ModsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fabric(self):
        p = make_jar(self.dir / "sodium.jar", {"fabric.mod.json": json.dumps({
            "id": "sodium", "name": "Sodium", "version": "0.5.3", "authors": ["jellysquid"],
            "depends": {"minecraft": ">=1.20"}})})
        m = mods.read_mod_metadata(p)
        self.assertEqual((m.name, m.version, m.mod_id, m.loaders), ("Sodium", "0.5.3", "sodium", ["fabric"]))
        self.assertEqual(m.authors, "jellysquid")

    def test_forge_toml_with_jar_version(self):
        toml = ('modLoader="javafml"\nloaderVersion="[47,)"\n[[mods]]\nmodId="jei"\n'
                'version="${file.jarVersion}"\ndisplayName="Just Enough Items"\n'
                'description=\'\'\'Item list\'\'\'\n')
        p = make_jar(self.dir / "jei.jar", {"META-INF/mods.toml": toml,
                                            "META-INF/MANIFEST.MF": "Implementation-Version: 15.2.0\n"})
        m = mods.read_mod_metadata(p)
        self.assertEqual((m.name, m.version, m.loaders), ("Just Enough Items", "15.2.0", ["forge"]))
        with mock.patch.object(mods, "tomllib", None):
            m = mods.read_mod_metadata(p)
            self.assertEqual((m.name, m.mod_id), ("Just Enough Items", "jei"))

    def test_neoforge_and_mcmod(self):
        p = make_jar(self.dir / "a.jar", {"META-INF/neoforge.mods.toml": '[[mods]]\nmodId="a"\nversion="1"\n'})
        self.assertEqual(mods.read_mod_metadata(p).loaders, ["neoforge"])
        p = make_jar(self.dir / "b.jar", {"mcmod.info": json.dumps({"modList": [{"modid": "b", "name": "B",
                                                                                    "version": "2"}]})})
        m = mods.read_mod_metadata(p)
        self.assertEqual((m.name, m.version, m.loaders), ("B", "2", ["forge"]))

    def test_broken_jar(self):
        p = self.dir / "broken.jar"
        p.write_bytes(b"not a zip")
        self.assertEqual(mods.read_mod_metadata(p).name, "broken")

    def test_toggle_and_list(self):
        make_jar(self.dir / "x.jar", {"fabric.mod.json": '{"id":"x","version":"1"}'})
        items = mods.list_content(self.dir)
        self.assertEqual(len(items), 1)
        mods.set_enabled(items[0], False)
        self.assertTrue((self.dir / "x.jar.disabled").exists())
        items = mods.list_content(self.dir)
        self.assertFalse(items[0].enabled)
        self.assertEqual(items[0].filename, "x.jar")
        mods.set_enabled(items[0], True)
        self.assertTrue((self.dir / "x.jar").exists())

    def test_loader_mismatch(self):
        fab = mods.ModFile(Path("a.jar"), "a", loaders=["fabric"])
        self.assertFalse(mods.loader_mismatch(fab, "fabric"))
        self.assertFalse(mods.loader_mismatch(fab, "quilt"))
        self.assertTrue(mods.loader_mismatch(mods.ModFile(Path("b.jar"), "b", loaders=["forge"]), "fabric"))


class InstanceTest(unittest.TestCase):
    def test_lifecycle(self):
        with tempfile.TemporaryDirectory() as d:
            paths = Paths(Path(d)).ensure()
            mgr = InstanceManager(paths)
            a = mgr.create("My: Pack?", "1.20.1", "fabric", "0.15.0")
            self.assertTrue(a.mods_dir.is_dir())
            self.assertEqual(a.root.name, "My_ Pack_")
            b = mgr.create("My: Pack?", "1.20.1")
            self.assertNotEqual(a.root, b.root)
            c = mgr.copy(a, "Copy")
            self.assertEqual({i.name for i in mgr.list()}, {"My: Pack?", "Copy"})
            mgr.delete(b)
            mgr.delete(c)
            self.assertEqual([i.name for i in mgr.list()], ["My: Pack?"])

    def test_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            paths = Paths(Path(d)).ensure()
            cfg = Config(paths)
            cfg.settings.max_memory = 6144
            cfg.save()
            data = json.loads(paths.settings_file.read_text())
            data["unknown_key"] = 1
            paths.settings_file.write_text(json.dumps(data))
            self.assertEqual(Config(paths).settings.max_memory, 6144)


class SpeedPathTest(unittest.TestCase):
    def test_file_ok_fast_and_verify(self):
        from vanquish import net
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a"
            f.write_bytes(b"hello")
            good = net.sha1_of(f)
            self.assertTrue(net.file_ok(f, "0" * 40, 5))            # fast: size matches, hash not read
            self.assertFalse(net.file_ok(f, "0" * 40, 5, verify=True))
            self.assertTrue(net.file_ok(f, good, 5, verify=True))
            self.assertFalse(net.file_ok(f, good, 6))
            self.assertFalse(net.file_ok(f, "0" * 40))              # no size: always hashed
            self.assertFalse(net.file_ok(Path(d) / "missing"))

    def test_manifest_cache_expires(self):
        with tempfile.TemporaryDirectory() as d:
            paths = Paths(Path(d)).ensure()
            cache = paths.cache / "version_manifest_v2.json"
            cache.write_text(json.dumps({"versions": [{"id": "old"}]}))
            with mock.patch.object(versions.net, "get_json", return_value={"versions": [{"id": "new"}]}):
                self.assertEqual(versions.get_manifest(paths)["versions"][0]["id"], "old")
                os.utime(cache, (0, 0))
                self.assertEqual(versions.get_manifest(paths)["versions"][0]["id"], "new")
            os.utime(cache, (0, 0))
            with mock.patch.object(versions.net, "get_json", side_effect=versions.net.NetworkError("offline")):
                self.assertEqual(versions.get_manifest(paths)["versions"][0]["id"], "new")  # offline fallback


class MrpackTest(unittest.TestCase):
    def _pack(self, d: Path, files, deps=None, extra=None):
        index = {"formatVersion": 1, "game": "minecraft", "name": "Test Pack", "versionId": "1",
                 "files": files, "dependencies": deps or {"minecraft": "1.20.1", "fabric-loader": "0.15.0"}}
        entries = {"modrinth.index.json": json.dumps(index)}
        entries.update(extra or {})
        return make_jar(d / "pack.mrpack", entries)

    def test_install(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            paths = Paths(d / "data").ensure()
            mgr = InstanceManager(paths)
            pack = self._pack(d, [{"path": "mods/a.jar", "downloads": ["https://cdn.modrinth.com/a.jar"],
                                   "hashes": {"sha1": "0"}, "fileSize": 1},
                                  {"path": "mods/server.jar", "env": {"client": "unsupported"},
                                   "downloads": ["https://cdn.modrinth.com/s.jar"]}],
                              extra={"overrides/config/x.cfg": "a=1", "overrides/../../evil": "x"})
            seen = []
            with mock.patch.object(mrpack.net, "download_many", lambda jobs, *a, **k: seen.extend(jobs)):
                inst = mrpack.install_pack(pack, mgr)
            self.assertEqual((inst.mc_version, inst.loader, inst.loader_version), ("1.20.1", "fabric", "0.15.0"))
            self.assertEqual([j.url for j in seen], ["https://cdn.modrinth.com/a.jar"])
            self.assertEqual((inst.game_dir / "config" / "x.cfg").read_text(), "a=1")
            self.assertFalse((d / "evil").exists())

    def test_rejects_traversal_and_untrusted_host(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            mgr = InstanceManager(Paths(d / "data").ensure())
            bad = self._pack(d, [{"path": "../../x.jar", "downloads": ["https://cdn.modrinth.com/x"]}])
            with self.assertRaises(mrpack.PackError):
                mrpack.install_pack(bad, mgr)
            bad = self._pack(d, [{"path": "mods/x.jar", "downloads": ["http://evil.example/x"]}])
            with self.assertRaises(mrpack.PackError):
                mrpack.install_pack(bad, mgr)
            self.assertEqual(mgr.list(), [])  # failed imports are cleaned up

    def test_forge_pack_rejected(self):
        with self.assertRaises(mrpack.PackError):
            mrpack.pack_info({"dependencies": {"minecraft": "1.20.1", "forge": "47"}})


if __name__ == "__main__":
    unittest.main()
