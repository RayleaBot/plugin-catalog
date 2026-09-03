import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_catalog


class PackageInspectionTests(unittest.TestCase):
    def write_package(self, artifact: dict, flat: bool = False) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "plugin.zip"
        prefix = "" if flat else "raylea.echo/"
        with zipfile.ZipFile(path, "w") as package:
            package.writestr(prefix + "info.json", json.dumps({
                "id": "raylea.echo",
                "version": "0.4.0",
                "min_core_version": "0.4.0",
            }))
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
