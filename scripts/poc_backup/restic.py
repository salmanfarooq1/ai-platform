"""The on-demand restic service (compose profile `backup`): one local repository, one tagged snapshot per backup."""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.poc_lib.context import StackContext
from scripts.poc_lib.runner import CommandError
from scripts.poc_lib.up import PocError

PROFILE = "backup"


def backup_args(stack: str, manifest_sha256: str) -> list[str]:
    """One backup of the one staged folder. The manifest hash is in the tag, so the snapshot names what it contains."""
    return ["backup", "/staging", "--tag", "poc", "--tag", f"stack-{stack}", "--tag", f"manifest-{manifest_sha256}",
            "--host", f"poc-{stack}", "--json"]


def private_dir(path: Path, *, fresh: bool = False) -> Path:
    """A real 0700 directory of ours (never a link). With `fresh`, any earlier contents are removed first."""
    if path.is_symlink():
        raise PocError("refusing a symbolic link where a private folder is expected")
    if fresh and path.exists():
        shutil.rmtree(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


class Restic:
    def __init__(self, context: StackContext) -> None:
        self.context = context
        self.repo = context.stack_dir / "backups"
        self.restore_dir = context.stack_dir / "restore"
        self.staging = context.stack_dir / "staging"

    def _prepare(self) -> None:
        for path in (self.repo, self.restore_dir, self.staging):  # bind-mount sources must exist and be ours
            if not path.exists():
                private_dir(path)

    def run(self, *args: str, output_file: Path | None = None, check: bool = True) -> Any:
        self._prepare()
        return self.context.compose("run", "--rm", "--no-deps", "-T", "restic", *args, profile=PROFILE,
                                    output_file=output_file, check=check)

    def ensure_repo(self) -> None:
        if self.run("cat", "config", check=False).returncode != 0:
            self.run("init")

    def backup(self, manifest_sha256: str) -> str:
        result = self.run(*backup_args(self.context.stack, manifest_sha256))
        for line in reversed(result.text.splitlines()):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("message_type") == "summary" and row.get("snapshot_id"):
                return str(row["snapshot_id"])
        raise PocError("restic did not report a snapshot id")

    def snapshots(self) -> list[dict[str, Any]]:
        """This stack's snapshots, newest first."""
        text = self.run("snapshots", "--json", "--tag", f"stack-{self.context.stack}").text
        try:
            rows = json.loads(text or "[]")
        except ValueError:
            raise PocError("restic returned unreadable snapshot data") from None
        return sorted(rows, key=lambda r: datetime.fromisoformat(str(r["time"]).replace("Z", "+00:00")), reverse=True)

    def dump(self, snapshot_id: str, name: str, output_file: Path) -> bytes:
        self.run("dump", snapshot_id, f"/staging/{name}", output_file=output_file)
        return output_file.read_bytes()

    def check(self) -> None:
        try:
            self.run("check", "--read-data")
        except CommandError:
            raise PocError("restic check --read-data failed: the repository data is damaged or unreadable") from None

    def restore(self, ref: Any) -> Path:
        """Restore the snapshot into a fresh private folder and return the host path of the restored staging folder."""
        private_dir(self.restore_dir, fresh=True)
        try:
            self.run("restore", ref.snapshot_id, "--target", "/restore")
        except CommandError:
            raise PocError("restic could not restore the snapshot") from None
        return self.restore_dir / "staging"

    def cleanup_restore(self) -> None:
        if self.restore_dir.exists() and not self.restore_dir.is_symlink():
            shutil.rmtree(self.restore_dir)
