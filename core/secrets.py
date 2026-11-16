"""Resolve named environment and protected file secret references."""

from __future__ import annotations

import os
import stat

from ports.models import SecretRef


class SecretRefError(RuntimeError):
    """A secret reference could not be safely resolved."""


class Secret:
    """A secret value whose string representations expose only its reference."""

    __slots__ = ("_value", "_ref")

    def __init__(self, value: str, ref: SecretRef) -> None:
        self._value = value
        self._ref = ref

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"Secret({self._ref})"

    def __str__(self) -> str:
        return repr(self)


def resolve_secret(ref: SecretRef) -> Secret:
    """Resolve a reference without including secret contents in errors."""
    if ref.kind == "env":
        value = os.environ.get(ref.name)
        if value is None:
            raise SecretRefError("environment secret reference is unavailable")
        value = value.rstrip("\r\n")
        if not value:
            raise SecretRefError("secret value is empty")
        return Secret(value, ref)

    path = ref.name
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise SecretRefError("file secret must be a regular non-symlink file")
        if before.st_uid != os.getuid():
            raise SecretRefError("file secret has the wrong owner")
        if before.st_mode & 0o077:
            raise SecretRefError("file secret permissions are too loose")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            after = os.fstat(fd)
            if not stat.S_ISREG(after.st_mode) or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
                raise SecretRefError("file secret changed while it was opened")
            if after.st_uid != os.getuid() or after.st_mode & 0o077:
                raise SecretRefError("file secret ownership or permissions are unsafe")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                value = stream.read().decode("utf-8")
        finally:
            os.close(fd)
    except SecretRefError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise SecretRefError("file secret could not be safely resolved") from None
    value = value.rstrip("\r\n")
    if not value:
        raise SecretRefError("secret value is empty")
    return Secret(value, ref)


__all__ = ["Secret", "SecretRef", "SecretRefError", "resolve_secret"]
