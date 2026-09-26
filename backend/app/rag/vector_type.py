"""A minimal SQLAlchemy column type for pgvector's `vector(n)`.

Written instead of adding the `pgvector` package: that package pulls in numpy,
which would add roughly 25 MB to the Lambda bundle for the sake of two string
conversions. Vectors travel to Postgres as the text literal `[0.1,0.2,...]`
and come back the same way, so this type only formats and parses that.
Queries cast the bound parameter explicitly: `CAST(:q AS vector)`.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy.types import UserDefinedType


def to_pg_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def from_pg_literal(text: str) -> List[float]:
    body = text.strip()[1:-1].strip()
    return [float(x) for x in body.split(",")] if body else []


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dims: int):
        self.dims = dims

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dims})"

    def bind_processor(self, dialect):
        def process(value: Optional[Sequence[float]]):
            return None if value is None else to_pg_literal(value)
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            return from_pg_literal(value) if isinstance(value, str) else list(value)
        return process
