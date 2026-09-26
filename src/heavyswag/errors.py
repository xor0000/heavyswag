class HeavySwagError(Exception):
    """Base HeavySwagError"""


class IncludedRouterError(HeavySwagError):
    """Router include error"""


class RouteTreeError(HeavySwagError):
    """Route tree construction error"""


class SerializationError(HeavySwagError):
    """Request/response serialization error"""


class ValidationError(HeavySwagError):
    """A field's value or a field validator's own rules broke a
    `heavyswag.validation` constraint (e.g. `StrField`)."""
