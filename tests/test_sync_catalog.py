import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_catalog


class PackageInspectionTests(unittest.TestCase):
    def write_package(self, artifact: dict, flat: bool = False, **info) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "plugin.zip"
        prefix = "" if flat else "raylea.echo/"
        with zipfile.ZipFile(path, "w") as package:
            package.writestr(prefix + "info.json", json.dumps({
                "id": "raylea.echo",
                "version": "0.4.0",
                "manifest_version": "4",
                "min_core_version": "0.4.0",
            } | info))
            package.writestr(prefix + "artifact.json", json.dumps(artifact))
            package.writestr(prefix + "bin/raylea.echo.exe", b"fixture")
        return path

    def test_accepts_minimal_artifact_in_single_plugin_root(self):
        package = self.write_package({
            "artifact_version": "2",
            "target_platform": "windows-x64",
            "entry": "bin/raylea.echo.exe",
        })
        info = sync_catalog.inspect_package(package, "raylea.echo", "0.4.0", "windows-x64")
        self.assertEqual(info["min_core_version"], "0.4.0")

    def test_skips_previous_artifact_v2_shape(self):
        package = self.write_package({
            "artifact_version": "2",
            "target_platform": "windows-x64",
            "entry": "bin/raylea.echo.exe",
            "files": [],
        })
        self.assertIsNone(sync_catalog.inspect_package(package, "raylea.echo", "0.4.0", "windows-x64"))

    def test_skips_packages_for_earlier_cores(self):
        artifact = {
            "artifact_version": "2",
            "target_platform": "windows-x64",
            "entry": "bin/raylea.echo.exe",
        }
        for info in ({"manifest_version": "3"}, {"min_core_version": "0.4.0-beta.1"}, {"min_core_version": "0.3.1"}):
            with self.subTest(info=info):
                package = self.write_package(artifact, **info)
                self.assertIsNone(sync_catalog.inspect_package(package, "raylea.echo", "0.4.0", "windows-x64"))

    def test_rejects_flat_zip(self):
        package = self.write_package({
            "artifact_version": "2",
            "target_platform": "windows-x64",
            "entry": "bin/raylea.echo.exe",
        }, flat=True)
        with self.assertRaisesRegex(ValueError, "top-level plugin directory"):
            sync_catalog.inspect_package(package, "raylea.echo", "0.4.0", "windows-x64")


if __name__ == "__main__":
    unittest.main()


class DependencyTests(unittest.TestCase):
    ARTIFACT = {"artifact_version": "2", "target_platform": "windows-x64", "entry": "bin/raylea.genshin.exe"}
    DEPENDENCIES = [{"id": "raylea.mihoyo-accounts", "requirement": "recommended", "reason": "体力与签到需要米游社登录"}]

    def write_package(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "plugin.zip"
        with zipfile.ZipFile(path, "w") as package:
            package.writestr("raylea.genshin/info.json", json.dumps({
                "id": "raylea.genshin",
                "version": "0.1.0",
                "manifest_version": "4",
                "min_core_version": "0.4.0",
                "dependencies": self.DEPENDENCIES,
            }))
            package.writestr("raylea.genshin/artifact.json", json.dumps(self.ARTIFACT))
            package.writestr("raylea.genshin/bin/raylea.genshin.exe", b"fixture")
        return path

    def test_release_carries_the_package_dependencies(self):
        package = self.write_package()

        def fake_download(_url: str, target: Path) -> str:
            shutil.copyfile(package, target)
            return "0" * 64

        release = {
            "tag_name": "v0.1.0",
            "published_at": "2026-10-01T00:00:00Z",
            "assets": [{
                "name": "raylea.genshin-0.1.0-windows-x64.zip",
                "browser_download_url": "https://github.com/RayleaBot/genshin/releases/download/v0.1.0/raylea.genshin-0.1.0-windows-x64.zip",
            }],
        }
        with mock.patch.object(sync_catalog, "download", fake_download):
            current = sync_catalog.build_release({"id": "raylea.genshin"}, release)
        self.assertEqual(current["dependencies"], self.DEPENDENCIES)

    def test_rejects_invalid_dependencies(self):
        for dependencies in (
            [{"id": "raylea.genshin", "requirement": "required"}],
            [{"id": "raylea.mihoyo-accounts", "requirement": "optional"}],
            self.DEPENDENCIES * 2,
        ):
            with self.subTest(dependencies=dependencies), self.assertRaises(ValueError):
                sync_catalog.validate_dependencies("raylea.genshin", dependencies)
        sync_catalog.validate_dependencies("raylea.genshin", self.DEPENDENCIES)
