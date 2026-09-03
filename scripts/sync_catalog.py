#!/usr/bin/env python3
"""Build catalog.json from each configured plugin's latest GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PLATFORMS = ("windows-x64", "linux-x64", "macos-arm64")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def request_bytes(url: str, token: str = "") -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RayleaBot-plugin-catalog",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def download(url: str, target: Path) -> str:
    headers = {"User-Agent": "RayleaBot-plugin-catalog"}
    digest = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
        with target.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
    return digest.hexdigest()


def inspect_package(path: Path, plugin_id: str, version: str, platform: str) -> dict | None:
    with zipfile.ZipFile(path) as package:
        names = [item.filename for item in package.infolist() if not item.is_dir()]
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        if len(roots) != 1 or any("/" not in name for name in names):
            raise ValueError(f"{path.name}: package must contain one top-level plugin directory")
        root = roots.pop()
        if root != plugin_id:
            raise ValueError(f"{path.name}: package root must be named {plugin_id}")
        info_name = f"{root}/info.json"
        artifact_name = f"{root}/artifact.json"
        if info_name not in names or artifact_name not in names:
            raise ValueError(f"{path.name}: plugin directory must contain info.json and artifact.json")
        info = json.loads(package.read(info_name))
        artifact = json.loads(package.read(artifact_name))

    if info.get("id") != plugin_id or info.get("version") != version:
        raise ValueError(f"{path.name}: info.json identity does not match the release")
    if artifact.get("artifact_version") != "2" or set(artifact) != {"artifact_version", "target_platform", "entry"}:
        return None
    if artifact.get("target_platform") != platform:
        raise ValueError(f"{path.name}: artifact.json targets the wrong platform")
    if not isinstance(artifact.get("entry"), str) or not artifact["entry"].strip():
        raise ValueError(f"{path.name}: artifact.json entry is missing")
    if f"{root}/{artifact['entry']}" not in names:
        raise ValueError(f"{path.name}: artifact entry is missing from the package")
    return info


def build_release(plugin: dict, release: dict) -> dict | None:
    version = str(release.get("tag_name", "")).removeprefix("v")
    if not version:
        return None

    expected_names = {
        f"{plugin['id']}-{version}-{platform}.zip": platform for platform in SUPPORTED_PLATFORMS
    }
    assets_by_name = {asset.get("name"): asset for asset in release.get("assets", [])}
    selected = [(name, platform, assets_by_name[name]) for name, platform in expected_names.items() if name in assets_by_name]
    if not selected:
        return None

    assets = []
    package_info = None
    with tempfile.TemporaryDirectory(prefix="raylea-catalog-") as temp_dir:
        for name, platform, asset in selected:
            url = asset.get("browser_download_url", "")
            if not url.startswith("https://github.com/"):
                raise ValueError(f"{name}: release asset URL must use GitHub HTTPS")
            package_path = Path(temp_dir) / name
            archive_sha256 = download(url, package_path)
            info = inspect_package(package_path, plugin["id"], version, platform)
            if info is None:
                return None
            if package_info is None:
                package_info = info
            elif info.get("min_core_version") != package_info.get("min_core_version"):
                raise ValueError(f"{name}: min_core_version differs between platform packages")
            assets.append({"platform": platform, "url": url, "archive_sha256": archive_sha256})

    min_core_version = str((package_info or {}).get("min_core_version", "")).strip()
    if not min_core_version:
        raise ValueError(f"{plugin['id']} {version}: min_core_version is missing")
    return {
        "version": version,
        "published_at": release["published_at"],
        "min_core_version": min_core_version,
        "assets": assets,
    }


def build_catalog(sources: dict, token: str) -> dict:
    publisher = sources["publisher"]
    entries = []
    for plugin in sources["plugins"]:
        repository = plugin["repository"]
        release_url = f"https://api.github.com/repos/{repository}/releases/latest"
        try:
            release = json.loads(request_bytes(release_url, token))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                release = None
            else:
                raise

        entry = {
            "id": plugin["id"],
            "name": plugin["name"],
            "summary": plugin["summary"],
            "publisher": publisher,
            "repository_url": f"https://github.com/{repository}",
            "license": plugin["license"],
            "keywords": plugin["keywords"],
            "recommended": plugin["recommended"],
        }
        for optional in ("category", "icon_url"):
            if plugin.get(optional):
                entry[optional] = plugin[optional]
        if release:
            current_release = build_release(plugin, release)
            if current_release:
                entry["current_release"] = current_release
        entries.append(entry)
    return {"catalog_version": "2", "entries": entries}


def validate_catalog(catalog: dict, sources: dict) -> None:
    if catalog.get("catalog_version") != "2":
        raise ValueError("catalog version is not 2")
    expected_ids = [plugin["id"] for plugin in sources["plugins"]]
    entries = catalog.get("entries")
    if not isinstance(entries, list) or [entry.get("id") for entry in entries] != expected_ids:
        raise ValueError("catalog entries do not match sources.json order")
    for entry in entries:
        release = entry.get("current_release")
        if release is None:
            continue
        assets = release.get("assets", [])
        platforms = [asset.get("platform") for asset in assets]
        if not assets or len(platforms) != len(set(platforms)):
            raise ValueError(f"{entry['id']}: current release assets are empty or duplicated")
        for asset in assets:
            if asset.get("platform") not in SUPPORTED_PLATFORMS:
                raise ValueError(f"{entry['id']}: unsupported platform {asset.get('platform')}")
            if not str(asset.get("url", "")).startswith("https://github.com/"):
                raise ValueError(f"{entry['id']}: asset URL must use GitHub HTTPS")
            if not SHA256_RE.fullmatch(str(asset.get("archive_sha256", ""))):
                raise ValueError(f"{entry['id']}: invalid archive SHA-256")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    sources = load_json(ROOT / "sources.json")
    catalog_path = ROOT / "catalog.json"
    if args.validate_only:
        validate_catalog(load_json(catalog_path), sources)
        return

    catalog = build_catalog(sources, os.environ.get("GITHUB_TOKEN", ""))
    validate_catalog(catalog, sources)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
