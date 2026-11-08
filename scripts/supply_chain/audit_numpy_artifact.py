"""Reproduce the reviewed NumPy source, compiler-closure and exact wheel-member audit.

Run after building the unmodified hash-verified 2.4.2 sdist with meson-python.
The local build supplies compiler dependency evidence, not a replacement wheel.
"""
import argparse
import gzip
import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

SOURCE_HASH = "659a6107e31a83c4e33f763942275fd278b21d095094044eb35569e86a21ddae"
WHEEL_HASH = "c02ef4401a506fb60b411467ad501e1429a3487abca4664871d9ae0b46c8ba32"
CC0 = ("random/src/splitmix64", "highway/hwy/contrib/random/random-inl.h")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdist", "source", "wheel", "build", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    assert hashlib.sha256(args.sdist.read_bytes()).hexdigest() == SOURCE_HASH
    assert hashlib.sha256(args.wheel.read_bytes()).hexdigest() == WHEEL_HASH
    args.output.mkdir(parents=True, exist_ok=True)
    checked = 0
    with tarfile.open(args.sdist) as archive:
        for member in archive.getmembers():
            if member.isfile():
                relative = Path(member.name).relative_to("numpy-2.4.2")
                assert args.source.joinpath(relative).read_bytes() == archive.extractfile(member).read(), relative
                checked += 1
    commands = json.loads((args.build / "compile_commands.json").read_text())
    assert not any(any(code in row["file"] for code in CC0) for row in commands)
    complete = subprocess.check_output(["ninja", "-C", str(args.build), "-n"], text=True)
    assert "no work to do" in complete, complete
    dependencies = subprocess.check_output(["ninja", "-C", str(args.build), "-t", "deps"], text=True)
    assert dependencies and not any(code in dependencies for code in CC0)
    (args.output / "numpy-compiler-commands.json").write_text(json.dumps(commands, indent=2) + "\n")
    with gzip.open(args.output / "numpy-compiler-dependencies.txt.gz", "wt") as out:
        out.write(dependencies)
    with zipfile.ZipFile(args.wheel) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        forbidden = [name for name in names if any(code in name for code in CC0) and "/licenses/" not in name]
        assert not forbidden, forbidden
        # Preserve the original publisher notices; the correction never edits them.
        notices = [name for name in names if "/licenses/" in name]
        inventory = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in names}
        (args.output / "numpy-upstream-wheel-members.json").write_text(json.dumps(inventory, indent=2) + "\n")
        symbols = []
        binaries = 0
        for name in names:
            if name.startswith("numpy/") and name.endswith((".so", ".a")):
                target = args.output / "symbol-input"
                target.write_bytes(archive.read(name))
                result = subprocess.run(["nm", "-a", str(target)], capture_output=True, text=True)
                assert result.returncode == 0, name
                bad = [line for line in result.stdout.splitlines()
                       if any(term in line.lower() for term in ("splitmix64", "xoshiro", "random-inl"))]
                assert not bad, (name, bad)
                sources = [line for line in result.stdout.splitlines() if " a " in line and line.endswith((".c", ".cc", ".cpp"))]
                symbols.extend([name, *sources])
                binaries += 1
        target.unlink()
        (args.output / "numpy-upstream-binary-source-symbols.txt").write_text("\n".join(symbols) + "\n")
    print("sdist SHA256:", SOURCE_HASH)
    print("official wheel SHA256:", WHEEL_HASH)
    print("unmodified sdist files verified:", checked)
    print("compiler commands:", len(commands))
    print("compiler dependency bytes:", len(dependencies.encode()))
    print("official wheel members:", len(names), "original notices retained:", len(notices))
    print("official NumPy binaries/static libraries inspected:", binaries)
    print("Neither CC0 implementation occurs in compiler source/header inputs or official wheel source members/symbols.")
    print("The wheel audit and upstream source/build selection support the artifact-specific correction; the local wheel is not substituted.")


if __name__ == "__main__":
    main()
