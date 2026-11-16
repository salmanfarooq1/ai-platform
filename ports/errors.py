"""Errors shared by module ports."""


class ModuleDisabled(RuntimeError):
    """Raised when an optional module contract is called while its module is off."""


class UnknownModel(LookupError):
    """The requested model alias or model use is not available."""


class ModelDigestMismatch(RuntimeError):
    """The local provider's model digest differs from the reviewed lock."""


class UnpricedModel(RuntimeError):
    """A hosted model has no configured price."""


class ResidencyUnknown(RuntimeError):
    """A hosted model's processing region cannot be established."""


class ModelHostNotAllowed(RuntimeError):
    """A hosted model endpoint is outside the application's configured host allow-list."""
