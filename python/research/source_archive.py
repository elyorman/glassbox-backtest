"""Preserve exact Python runtimes and verify frozen stock evidence with its own code."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from tempfile import TemporaryDirectory


def _source_paths(root):
    paths = []
    if root.is_symlink():
        raise ValueError("Source root cannot be a symlink")
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("Source symlinks are not archived or executed")
        if path.is_file() and path.suffix == ".py":
            paths.append(path)
    return sorted(paths)


def verify_source_archive(archive):
    archive = Path(archive)
    if archive.is_symlink():
        raise ValueError("Archive cannot be a symlink")
    manifest_path = archive / "SOURCE_ARCHIVE.json"
    if manifest_path.is_symlink():
        raise ValueError("Archive manifest cannot be a symlink")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Archive manifest must be an object")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Archive requires a nonempty source manifest")
    for name, expected in files.items():
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name
                or path.as_posix() != name or path.suffix != ".py"):
            raise ValueError("Unsafe archive source path")
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("Invalid source hash")
    paths = _source_paths(archive)
    observed = {path.relative_to(archive).as_posix(): sha256(path.read_bytes()).hexdigest() for path in paths}
    if set(observed) != set(files):
        raise ValueError("Archive source set changed")
    if observed != files:
        raise ValueError("Archive source hash changed")
    return manifest


def archive_sources(root, output):
    """Archive Python files only; secrets, caches, research outputs and datasets are excluded."""
    root, output = Path(root), Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("Archive output already exists")
    source = root / "python"
    if output.resolve().is_relative_to(source.resolve()):
        raise ValueError("Archive output cannot be inside its source tree")
    paths = _source_paths(source)
    if not paths:
        raise ValueError("No Python sources to preserve")
    raw = {path.relative_to(source).as_posix(): path.read_bytes() for path in paths}
    manifest = {"schema_version": 1, "python_version": sys.version.split()[0],
                "files": {name: sha256(body).hexdigest() for name, body in raw.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".source-archive-", dir=output.parent) as temporary:
        staging = Path(temporary)
        for name, body in raw.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        (staging / "SOURCE_ARCHIVE.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        verify_source_archive(staging)
        # Exclusive directory reservation; never replace another archive.
        output.mkdir()
        for path in sorted(staging.rglob("*")):
            destination = output / path.relative_to(staging)
            if path.is_dir():
                destination.mkdir(exist_ok=True)
            else:
                os.link(path, destination)
    verify_source_archive(output)
    return manifest


def verify_stock_campaign(archive, campaign):
    """Run the fixed verifier from a trusted local archive, bound to the campaign's source set.

    Checksums check integrity, not authorship. Only use archives whose provenance
    you trust. This executes no new performance experiment and changes no files.
    """
    archive, campaign = Path(archive).resolve(), Path(campaign).resolve()
    manifest = verify_source_archive(archive)
    plan = json.loads((campaign / "EXPERIMENT_PLAN.json").read_text(encoding="utf-8"))
    if manifest["files"] != plan.get("source_hashes"):
        raise ValueError("Archive differs from the campaign's frozen source hashes")
    script = archive / "research/stock_campaign.py"
    if not script.is_file():
        raise ValueError("Archived stock verifier is missing")
    # Bytecode/native artifacts are outside the source manifest. Even with
    # PYTHONDONTWRITEBYTECODE Python can load cached .pyc files, so execute a
    # clean source-only copy instead of importing directly from the archive.
    with TemporaryDirectory(prefix="quant-frozen-replay-") as temporary:
        runtime = Path(temporary)
        for name, digest in manifest["files"].items():
            body = (archive / name).read_bytes()
            if sha256(body).hexdigest() != digest:
                raise ValueError("Archive source changed while preparing replay")
            destination = runtime / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        environment = dict(os.environ, PYTHONPATH=str(runtime), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, str(runtime / "research/stock_campaign.py"),
                                 "verify", "--output", str(campaign)], cwd=runtime,
                                env=environment, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("Archived campaign verification failed: " + result.stderr[-1500:])
    return json.loads(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    creator = commands.add_parser("create")
    creator.add_argument("--root", type=Path, default=Path.cwd())
    creator.add_argument("--output", type=Path, required=True)
    verifier = commands.add_parser("verify")
    verifier.add_argument("archive", type=Path)
    replay = commands.add_parser("verify-stock")
    replay.add_argument("--archive", type=Path, required=True)
    replay.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = archive_sources(args.root, args.output)
        elif args.command == "verify":
            result = verify_source_archive(args.archive)
        else:
            result = verify_stock_campaign(args.archive, args.campaign)
        print(json.dumps({"verified_sources": len(result["files"])} if "files" in result else result))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(f"Source verification error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
