"""Restore trusts public bytes and their derived id; never an id on its own."""
from collections.abc import Mapping

from core.settings import Settings, read_signing_key_file
from evidence.receipts import Keyring, decode_key, key_id_of


def validate_restore_key(identity: Mapping[str, str], settings: Settings) -> None:
    """Require an existing active private key and exact explicitly trusted backup public key.

    File existence is rechecked even for cached Settings: restoring must never use
    an ephemeral key or regenerate an absent recovery file.
    """
    try:
        private = settings.signing_key_text
        if settings.receipt_signing_key_file is not None:
            if read_signing_key_file(settings.receipt_signing_key_file) != private:
                raise ValueError("changed key file")
        if not private:
            raise ValueError("missing private key")
        public = decode_key(identity["public_key"])
        kid = identity["key_id"]
        if key_id_of(public) != kid:
            raise ValueError("public key id mismatch")
        ring = Keyring.from_private_text(private, [decode_key(key) for key in settings.previous_receipt_keys])
        if ring.public_raw(kid) != public:
            raise ValueError("backup public key is not trusted")
    except (KeyError, TypeError, ValueError):
        raise ValueError("restore requires the matching active key or exact trusted previous public key and an existing private key") from None
