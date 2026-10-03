"""The stand-in, and the reason this fixture cannot have darkroom's defect."""

from __future__ import annotations

from typing import Any, Mapping


class FakePool:
    """Answers the two statements this service's tests make, from a dict."""

    def __init__(self) -> None:
        self.rows: dict[str, Mapping[str, Any]] = {}

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        # The spelling is the same spelling a real cleanup uses, and there is no
        # database behind it. That is the whole point: the hazard needs a shared
        # SERVER, and this has none.
        if "delete from" in sql:
            self.rows.pop(str(params[0]), None)
        elif "insert into" in sql:
            self.rows[str(params[0])] = {"id": params[0]}
