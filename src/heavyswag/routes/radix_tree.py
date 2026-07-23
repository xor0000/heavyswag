from typing import Any, NamedTuple

from heavyswag.constants import HttpMethod
from heavyswag.errors import RouteTreeError
from heavyswag.routes.router import HeavyRouter, Route

type AnyRoute = Route[Any, Any, Any]


class Node:
    __slots__ = ("children", "label", "param_edge", "routes")

    def __init__(self, label: str) -> None:
        self.label = label
        self.children: dict[str, Node] = {}
        self.param_edge: ParamEdge | None = None
        self.routes: dict[HttpMethod, AnyRoute] = {}


class ParamEdge(NamedTuple):
    name: str
    node: Node


class MatchedRoute(NamedTuple):
    route: AnyRoute
    params: dict[str, str]


class CompressedRadixTree:
    """A char-compressed radix tree for HTTP route lookup"""

    __slots__ = ("_root",)

    def __init__(self, main_router: HeavyRouter) -> None:
        if main_router.prefix != "/":
            msg = (
                "CompressedRadixTree accepts only the main router, "
                "whose path is '/'."
            )
            raise RouteTreeError(msg)

        self._root = Node("")

        for path, route in self._collect(main_router, "/", frozenset()):
            self._insert(path, route)

    def search(self, method: HttpMethod, path: str) -> MatchedRoute | None:
        params: list[tuple[str, str]] = []
        route = self._search(self._root, path, 0, method, params)

        if route is None:
            return None

        return MatchedRoute(route=route, params=dict(params))

    def _search(
        self,
        node: Node,
        path: str,
        offset: int,
        method: HttpMethod,
        params: list[tuple[str, str]],
    ) -> AnyRoute | None:
        label = node.label
        label_end = offset + len(label)

        if path[offset:label_end] != label:
            return None

        if label_end == len(path):
            return node.routes.get(method)

        child = node.children.get(path[label_end])
        if child is not None:
            route = self._search(child, path, label_end, method, params)
            if route is not None:
                return route

        param_edge = node.param_edge
        if param_edge is not None:
            value_end = path.find("/", label_end)
            if value_end == -1:
                value_end = len(path)

            if value_end > label_end:
                params.append((param_edge.name, path[label_end:value_end]))
                route = self._search(
                    param_edge.node, path, value_end, method, params
                )
                if route is not None:
                    return route
                params.pop()

        return None

    def _collect(
        self,
        router: HeavyRouter,
        base: str,
        seen: frozenset[int],
    ) -> list[tuple[str, AnyRoute]]:
        if id(router) in seen:
            msg = f"Circular router inclusion detected at '{router.prefix}'."
            raise RouteTreeError(msg)

        seen = seen | {id(router)}

        collected = [
            (self._join(base, route.path), route) for route in router.routes
        ]

        for sub_router in router.added_routers:
            sub_base = self._join(base, sub_router.prefix)
            collected.extend(self._collect(sub_router, sub_base, seen))

        return collected

    def _join(self, base: str, segment: str) -> str:
        if segment == "/":
            return base

        trimmed = "" if base == "/" else base.rstrip("/")
        return f"{trimmed}{segment}"

    def _insert(self, path: str, route: AnyRoute) -> None:
        self._validate(path)

        node = self._root
        offset = 0
        length = len(path)

        while offset < length:
            if path[offset] == "{":
                close = path.index("}", offset)
                name = path[offset + 1 : close]

                if node.param_edge is None:
                    node.param_edge = ParamEdge(name, Node(""))
                elif node.param_edge.name != name:
                    msg = (
                        f"Conflicting path parameter in '{path}': "
                        f"expected '{node.param_edge.name}', got '{name}'."
                    )
                    raise RouteTreeError(msg)

                node = node.param_edge.node
                offset = close + 1
                continue

            param_start = path.find("{", offset)
            segment_end = param_start if param_start != -1 else length

            node = self._insert_static(node, path[offset:segment_end])
            offset = segment_end

        if route.method in node.routes:
            msg = f"Route '{route.method.name} {path}' is already registered."
            raise RouteTreeError(msg)

        node.routes[route.method] = route

    def _insert_static(self, node: Node, text: str) -> Node:
        while text:
            child = node.children.get(text[0])
            if child is None:
                new_node = Node(text)
                node.children[text[0]] = new_node
                return new_node

            common = self._common_prefix_length(child.label, text)
            if common < len(child.label):
                self._split(child, common)

            text = text[common:]
            node = child

        return node

    def _split(self, node: Node, at: int) -> None:
        tail_label = node.label[at:]
        tail = Node(tail_label)
        tail.children = node.children
        tail.param_edge = node.param_edge
        tail.routes = node.routes

        node.label = node.label[:at]
        node.children = {tail_label[0]: tail}
        node.param_edge = None
        node.routes = {}

    def _common_prefix_length(self, left: str, right: str) -> int:
        limit = min(len(left), len(right))
        index = 0
        while index < limit and left[index] == right[index]:
            index += 1
        return index

    def _validate(self, path: str) -> None:
        if not path.startswith("/"):
            msg = f"Path '{path}' must start with '/'."
            raise RouteTreeError(msg)

        if len(path) > 1 and path.endswith("/"):
            msg = f"Path '{path}' must not end with a trailing '/'."
            raise RouteTreeError(msg)

        if "//" in path:
            msg = f"Path '{path}' must not contain empty segments."
            raise RouteTreeError(msg)

        seen_params: set[str] = set()
        for segment in path.split("/")[1:]:
            self._validate_segment(path, segment, seen_params)

    def _validate_segment(
        self,
        path: str,
        segment: str,
        seen_params: set[str],
    ) -> None:
        is_param = segment.startswith("{") and segment.endswith("}")

        if not is_param:
            if "{" in segment or "}" in segment:
                msg = (
                    f"Path parameters must occupy a whole segment in '{path}'."
                )
                raise RouteTreeError(msg)
            return

        name = segment[1:-1]
        if not self._is_valid_param_name(name):
            msg = f"Invalid path parameter name '{name}' in '{path}'."
            raise RouteTreeError(msg)

        if name in seen_params:
            msg = f"Duplicate path parameter name '{name}' in '{path}'."
            raise RouteTreeError(msg)

        seen_params.add(name)

    def _is_valid_param_name(self, name: str) -> bool:
        if not name:
            return False

        first = name[0]
        if first != "_" and not ("a" <= first <= "z" or "A" <= first <= "Z"):
            return False

        for char in name[1:]:
            is_digit = "0" <= char <= "9"
            is_alpha = "a" <= char <= "z" or "A" <= char <= "Z"
            if char != "_" and not is_alpha and not is_digit:
                return False

        return True
