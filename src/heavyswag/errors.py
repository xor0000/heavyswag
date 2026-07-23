class HeavySwagError(Exception):
    """Base HeavySwagError"""


class IncludedRouterError(HeavySwagError):
    """Router include error"""


class RouteTreeError(HeavySwagError):
    """Route tree construction error"""


class SerializationError(HeavySwagError):
    """Request/response serialization error"""
