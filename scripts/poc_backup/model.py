"""Plain data for backups: what the manifest says about the database, and the proofs `down` binds to."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DbState:
    """What a database holds, in the terms the manifest records: schema head, a row count for every application table,
    each tenant's decision-chain head and checkpoints, and the objects the rows point to."""

    schema_head: str
    counts: Mapping[str, int]
    heads: Sequence[Sequence[Any]]  # [tenant_id, position, row_hash]
    checkpoints: Sequence[Sequence[Any]]  # [tenant_id, position, row_hash, reason]
    objects: Sequence[str]

    def comparable(self) -> dict[str, Any]:
        """Order-free form for equality checks. Excludes the schema head and objects, which have their own checks."""
        return {
            "counts": {str(k): int(v) for k, v in sorted(self.counts.items())},
            "heads": sorted((str(h[0]), int(h[1]), str(h[2])) for h in self.heads),
            "checkpoints": sorted((str(c[0]), int(c[1]), str(c[2]), str(c[3])) for c in self.checkpoints),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DbState":
        return cls(schema_head=str(data["schema_head"]), counts=dict(data["counts"]), heads=list(data["heads"]),
                   checkpoints=list(data["checkpoints"]), objects=list(data.get("objects", [])))


@dataclass(frozen=True)
class BackupRef:
    """The latest published backup, as read back from the repository: ids, digests, age and the manifest's state."""

    stack: str
    snapshot_id: str
    manifest_sha256: str
    created_at: datetime
    state: DbState


@dataclass(frozen=True)
class DownProof:
    """What the checks proved. `destroy` is given exactly this: the snapshot and manifest digests it was proved for."""

    stack: str
    snapshot_id: str
    manifest_sha256: str
