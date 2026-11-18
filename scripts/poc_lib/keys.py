"""Private host secrets, retained independently of runtime volumes and data backups.

The runner consumes compose_override() as an additional Compose file after its
service overrides. Only paths enter that file; private bytes never leave these files.
"""
import base64
import fcntl
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from core.settings import read_secret_at, secret_directory
from evidence.receipts import Keyring, decode_key


def _private_directory(parent: int, name: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise ValueError("unsafe secret directory")
    return fd


def _publish(directory: int, name: str, value: str) -> None:
    """Publish a fully written file without replacing an existing key, even on a race."""
    temporary = f".{name}-{secrets.token_hex(12)}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "w", encoding="ascii", closefd=False) as stream:
            stream.write(value)
            stream.flush()
            os.fsync(fd)
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
    finally:
        os.close(fd)
        os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)


@dataclass(frozen=True)
class StackSecrets:
    key_file: Path
    password_file: Path

    def public_identity(self) -> dict[str, str]:
        with secret_directory(self.key_file.parent) as directory:
            ring = Keyring.from_private_text(read_secret_at(directory, self.key_file.name, owned=True))
        key = ring.public_keys()[0]
        return {"key_id": key.key_id, "public_key": key.public_key}

    def compose_override(self) -> dict[str, Any]:
        """Read-only binds fail if missing instead of Docker creating a directory.

        Use an explicit path setting in both processes; an ambient inline source
        conflicts and fails Settings validation rather than silently winning.
        """
        return {"services": {
            service: {
                "environment": {"RECEIPT_SIGNING_KEY_FILE": "/run/secrets/receipt-signing.key"},
                "volumes": [{"type": "bind", "source": str(self.key_file),
                             "target": "/run/secrets/receipt-signing.key", "read_only": True,
                             "bind": {"create_host_path": False}}],
            }
            for service in ("api", "worker")
        }}


def ensure_stack_directory(root: Path, stack: str) -> None:
    """Create `.poc/<stack>` as a private directory (0700, owned, no symlink) and nothing else.

    `up` needs the folder to exist before it can open its lifecycle lock; the secrets themselves are then created
    by `ensure_stack_secrets` while the lock is held."""
    if re.fullmatch(r"[a-z][a-z0-9-]{2,30}", stack) is None:
        raise ValueError("invalid stack name")
    try:
        with secret_directory(root) as root_fd:
            poc_fd = _private_directory(root_fd, ".poc", create=True)
            try:
                os.close(_private_directory(poc_fd, stack, create=True))
            finally:
                os.close(poc_fd)
    except (OSError, ValueError):
        raise ValueError("missing, unsafe or malformed POC secret files") from None


def ensure_stack_secrets(root: Path, stack: str, *, restoring: bool = False) -> StackSecrets:
    """First up creates secrets once; restore requires both existing files.

    Lock the private directory during publication so concurrent up calls cannot
    read partially initialized state. Teardown must retain the entire .poc tree.
    """
    if re.fullmatch(r"[a-z][a-z0-9-]{2,30}", stack) is None:
        raise ValueError("invalid stack name")
    try:
        with secret_directory(root) as root_fd:
            poc_fd = _private_directory(root_fd, ".poc", create=not restoring)
            try:
                stack_fd = _private_directory(poc_fd, stack, create=not restoring)
                try:
                    fcntl.flock(stack_fd, fcntl.LOCK_EX)
                    for name in ("receipt-signing.key", "restic-password"):
                        try:
                            text = read_secret_at(stack_fd, name, owned=True)
                        except FileNotFoundError:
                            if restoring:
                                raise ValueError("missing recovery secret") from None
                            if name == "receipt-signing.key":
                                raw = Ed25519PrivateKey.generate().private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
                                text = base64.b64encode(raw).decode("ascii")
                            else:
                                text = secrets.token_urlsafe(48)
                            _publish(stack_fd, name, text)
                        if name == "receipt-signing.key":
                            decode_key(text)
                        elif len(text) < 32 or not text.isascii() or not text.isprintable():
                            raise ValueError("invalid repository password file")
                finally:
                    os.close(stack_fd)
            finally:
                os.close(poc_fd)
    except (OSError, ValueError):
        raise ValueError("missing, unsafe or malformed POC secret files") from None
    folder = Path(os.path.abspath(root)) / ".poc" / stack
    return StackSecrets(folder / "receipt-signing.key", folder / "restic-password")
