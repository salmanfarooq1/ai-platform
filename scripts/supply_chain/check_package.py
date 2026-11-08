#!/usr/bin/env python3
"""Inspect a hash-verified locked wheel without installing or importing it."""
import argparse
import hashlib
import io
import json
import tomllib
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path

from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[2]


def inspect(name: str) -> None:
    lock = tomllib.loads((ROOT / "poetry.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == name)
    version = package["version"]
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        metadata = json.load(response)
    supported = set(sys_tags())
    wheel = next(w for w in metadata["urls"] if w["filename"].endswith(".whl") and supported.intersection(parse_wheel_filename(w["filename"])[3]))
    hashes = {f["file"]: f["hash"] for f in package["files"]}
    expected = hashes[wheel["filename"]].removeprefix("sha256:")
    if wheel["digests"]["sha256"] != expected:
        raise ValueError("registry wheel hash disagrees with lock")
    with urllib.request.urlopen(wheel["url"], timeout=60) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError("downloaded wheel hash disagrees with lock")
    print(f"locked package: {name}=={version}\nsource: {url}\nwheel: {wheel['filename']}\nwheel sha256: {actual}")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        path = next(p for p in archive.namelist() if p.endswith(".dist-info/METADATA"))
        headers = BytesParser().parsebytes(archive.read(path))
        for key in ("License", "License-Expression", "License-File"):
            print(f"{key}: {headers.get_all(key, [])}")
        paths = [p for p in archive.namelist() if ".dist-info/" in p and Path(p).name.upper().startswith("LICENSE")]
        if not paths:
            raise ValueError("wheel contains no licence file")
        for path in paths:
            raw = archive.read(path)
            print(f"\n{path}\nlicense sha256: {hashlib.sha256(raw).hexdigest()}\n{raw.decode()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    inspect(parser.parse_args().package)


if __name__ == "__main__":
    main()
