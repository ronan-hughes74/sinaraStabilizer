# mirror.py

from typing import Any


class StabilizerMirror:
    """
    Local mirror of the Miniconf configuration tree.

    All GUI reads use this.
    Updated by Miniconf subscription callbacks.
    """

    def __init__(self) -> None:
        self._tree: dict[str, Any] = {}

    def update_subtree(self, path: list[str | int], value: Any) -> None:
        node = self._tree
        for key in path[:-1]:
            node = node.setdefault(str(key), {})
        node[str(path[-1])] = value

    def get(self, path: list[str | int]) -> Any:
        node = self._tree
        for key in path:
            node = node[str(key)]
        return node

    def get_full_tree(self) -> dict[str, Any]:
        return self._tree