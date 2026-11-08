"""Errors shared by module ports."""


class ModuleDisabled(RuntimeError):
    """Raised when an optional module contract is called while its module is off."""
