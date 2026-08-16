"""Typed wrappers around the pyarrow APIs used for table artifacts.

Pyarrow 19 ships without usable DataType/Table stubs under Pyright strict.
This facade keeps vendor objects internal and exposes stdlib-typed handles so
schema and Parquet helpers do not import ``pa.int64`` / ``pq.write_table``
directly. Wrappers call the same pyarrow functions with the same arguments.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from typing import BinaryIO, Protocol, TypeAlias, runtime_checkable

import pyarrow as pa
import pyarrow.parquet as pq

ArrowType: TypeAlias = object
"""Opaque pyarrow DataType handle. Tests may pass raw ``pa.int64()`` values."""

ArrowField: TypeAlias = object
"""Opaque pyarrow Field handle produced by ``field``."""

ArrowArray: TypeAlias = object
"""Opaque pyarrow Array handle produced by ``array``."""


@runtime_checkable
class ArrowColumn(Protocol):
    """Structural column handle exposing list conversion for round-trip tests."""

    def to_pylist(self) -> list[object]:
        """Return column values as a Python list.

        Returns:
            Cell values in row order.
        """
        ...


@runtime_checkable
class ArrowSchema(Protocol):
    """Structural schema handle exposing equality used by Parquet round-trips."""

    def equals(self, other: object, check_metadata: bool = False) -> bool:
        """Return whether this schema matches ``other``.

        Args:
            other: Schema handle to compare.
            check_metadata: When True, compare schema metadata bytes too.

        Returns:
            True when the schemas match.
        """
        ...


@runtime_checkable
class ArrowTable(Protocol):
    """Structural table handle returned by Parquet reads."""

    @property
    def schema(self) -> ArrowSchema:
        """Return the table schema handle."""
        ...

    @property
    def num_rows(self) -> int:
        """Return the number of stored rows."""
        ...

    @property
    def column_names(self) -> Sequence[str]:
        """Return ordered column names."""
        ...

    def column(self, name: str) -> ArrowColumn:
        """Return one named column handle.

        Args:
            name: Column name.

        Returns:
            Column handle supporting ``to_pylist``.
        """
        ...


def _call(factory: object, /, *args: object, **kwargs: object) -> object:
    """Invoke one vendor callable with the original positional and keyword arguments.

    Args:
        factory: pyarrow factory or method.
        *args: Positional arguments forwarded unchanged.
        **kwargs: Keyword arguments forwarded unchanged.

    Returns:
        Opaque vendor result.

    Raises:
        TypeError: If ``factory`` is not callable.
    """

    if not callable(factory):
        raise TypeError("vendor factory is not callable")
    return factory(*args, **kwargs)


def _member(owner: object, name: str) -> object:
    """Return one named attribute from a vendor module or handle.

    Args:
        owner: pyarrow module, parquet module, or opaque handle.
        name: Attribute name resolved at the call site.

    Returns:
        The attribute value.
    """

    return getattr(owner, name)


def _types_checker(name: str) -> object:
    """Return one ``pyarrow.types`` predicate by name.

    Args:
        name: Predicate attribute such as ``is_string``.

    Returns:
        Callable type predicate.
    """

    return _member(_member(pa, "types"), name)


def _require_schema(value: object) -> ArrowSchema:
    """Narrow an opaque vendor value to an Arrow schema handle.

    Args:
        value: Result of ``pyarrow.schema``.

    Returns:
        The same value typed as ``ArrowSchema``.

    Raises:
        TypeError: If the value lacks schema equality.
    """

    if not isinstance(value, ArrowSchema):
        raise TypeError("pyarrow.schema must return a schema handle")
    return value


def _require_table(value: object) -> ArrowTable:
    """Narrow an opaque vendor value to an Arrow table handle.

    Args:
        value: Result of ``pyarrow.table`` or ``pyarrow.parquet.read_table``.

    Returns:
        The same value typed as ``ArrowTable``.

    Raises:
        TypeError: If the value lacks table attributes.
    """

    if not isinstance(value, ArrowTable):
        raise TypeError("pyarrow table factory must return a table handle")
    return value


def int64() -> ArrowType:
    """Return the Arrow int64 type used for integer columns and row indexes.

    Returns:
        Opaque int64 type handle from ``pa.int64()``.
    """

    return _call(_member(pa, "int64"))


def string() -> ArrowType:
    """Return the Arrow string type used for text, formulas, and provenance.

    Returns:
        Opaque string type handle from ``pa.string()``.
    """

    return _call(_member(pa, "string"))


def float64() -> ArrowType:
    """Return the Arrow float64 type used for floating-point columns.

    Returns:
        Opaque float64 type handle from ``pa.float64()``.
    """

    return _call(_member(pa, "float64"))


def bool_() -> ArrowType:
    """Return the Arrow boolean type used for boolean columns.

    Returns:
        Opaque boolean type handle from ``pa.bool_()``.
    """

    return _call(_member(pa, "bool_"))


def decimal128(precision: int, scale: int) -> ArrowType:
    """Return a decimal128 type with the same precision and scale as ``pa.decimal128``.

    Args:
        precision: Decimal precision forwarded to pyarrow.
        scale: Decimal scale forwarded to pyarrow.

    Returns:
        Opaque decimal128 type handle.
    """

    return _call(_member(pa, "decimal128"), precision, scale)


def date32() -> ArrowType:
    """Return the Arrow date32 type used for calendar dates.

    Returns:
        Opaque date32 type handle from ``pa.date32()``.
    """

    return _call(_member(pa, "date32"))


def timestamp(unit: str, *, tz: str) -> ArrowType:
    """Return an Arrow timestamp type with the same unit and timezone as ``pa.timestamp``.

    Args:
        unit: Timestamp unit forwarded to pyarrow (artifact pin is microseconds).
        tz: Timezone name forwarded to pyarrow.

    Returns:
        Opaque timestamp type handle.
    """

    return _call(_member(pa, "timestamp"), unit, tz=tz)


def field(name: str, dtype: ArrowType, *, nullable: bool) -> ArrowField:
    """Build one schema field with the same arguments as ``pa.field``.

    Args:
        name: Column name.
        dtype: Opaque Arrow type handle.
        nullable: Nullability forwarded to pyarrow.

    Returns:
        Opaque field handle.
    """

    return _call(_member(pa, "field"), name, dtype, nullable=nullable)


def schema(fields: Sequence[object], *, metadata: Mapping[bytes, bytes]) -> ArrowSchema:
    """Build one schema from fields and metadata with the same arguments as ``pa.schema``.

    Args:
        fields: Ordered field handles from ``field``.
        metadata: Schema-level metadata bytes, including schema version.

    Returns:
        Schema handle exposing ``equals``.
    """

    return _require_schema(_call(_member(pa, "schema"), fields, metadata=metadata))


def array(values: Sequence[object], *, dtype: ArrowType) -> ArrowArray:
    """Build one typed array with the same arguments as ``pa.array``.

    Args:
        values: Cell values in row order, including nulls.
        dtype: Opaque Arrow type handle passed as pyarrow ``type``.

    Returns:
        Opaque array handle.
    """

    return _call(_member(pa, "array"), values, type=dtype)


def table(arrays: Mapping[str, ArrowArray], *, schema: ArrowSchema) -> ArrowTable:
    """Build one table with the same arguments as ``pa.table``.

    Args:
        arrays: Column name to array handle mapping.
        schema: Explicit schema handle including provenance columns.

    Returns:
        Table handle used for Parquet writes.
    """

    return _require_table(_call(_member(pa, "table"), arrays, schema=schema))


def write_table(
    table: ArrowTable,
    destination: BinaryIO,
    *,
    compression: str,
    use_dictionary: bool,
    write_statistics: bool,
    row_group_size: int,
) -> None:
    """Write one table to a binary buffer with the same arguments as ``pq.write_table``.

    Args:
        table: Table handle from ``table``.
        destination: In-memory binary buffer.
        compression: Codec name forwarded to pyarrow.
        use_dictionary: Dictionary encoding flag forwarded to pyarrow.
        write_statistics: Statistics flag forwarded to pyarrow.
        row_group_size: Row-group size forwarded to pyarrow.
    """

    _call(
        _member(pq, "write_table"),
        table,
        destination,
        compression=compression,
        use_dictionary=use_dictionary,
        write_statistics=write_statistics,
        row_group_size=row_group_size,
    )


def read_table(data: bytes) -> ArrowTable:
    """Read one Parquet payload with the same ``pq.read_table`` source as in-memory bytes.

    Args:
        data: Exact Parquet bytes.

    Returns:
        Table handle preserving stored types.

    Raises:
        TypeError: If pyarrow does not return a table handle.
    """

    return _require_table(_call(_member(pq, "read_table"), io.BytesIO(data)))


def is_string(arrow_type: ArrowType) -> bool:
    """Return whether ``arrow_type`` is an Arrow string type.

    Args:
        arrow_type: Opaque type handle.

    Returns:
        True when ``pa.types.is_string`` accepts the handle.
    """

    return bool(_call(_types_checker("is_string"), arrow_type))


def is_int64(arrow_type: ArrowType) -> bool:
    """Return whether ``arrow_type`` is an Arrow int64 type.

    Args:
        arrow_type: Opaque type handle.

    Returns:
        True when ``pa.types.is_int64`` accepts the handle.
    """

    return bool(_call(_types_checker("is_int64"), arrow_type))


def is_floating(arrow_type: ArrowType) -> bool:
    """Return whether ``arrow_type`` is an Arrow floating-point type.

    Args:
        arrow_type: Opaque type handle.

    Returns:
        True when ``pa.types.is_floating`` accepts the handle.
    """

    return bool(_call(_types_checker("is_floating"), arrow_type))


def is_boolean(arrow_type: ArrowType) -> bool:
    """Return whether ``arrow_type`` is an Arrow boolean type.

    Args:
        arrow_type: Opaque type handle.

    Returns:
        True when ``pa.types.is_boolean`` accepts the handle.
    """

    return bool(_call(_types_checker("is_boolean"), arrow_type))
