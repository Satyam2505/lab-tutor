"""Parse student submissions into structured, validated fields.

This layer makes no correctness judgment -- that is Tier 1's job. Its only
question is "is this a well-formed number/series at all?", and when the
answer is no it says so plainly instead of guessing.

The guessing rule matters. `"12,34"` could be twelve-point-three-four or
two values; `"1.2.3"` could be a typo for either. Silently picking one and
feeding it to Tier 1 would produce a confident diagnosis of a value the
student never wrote. Every ambiguous input is therefore rejected with a
message naming the field.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

#: Trailing units students commonly leave in a numeric field.
_UNIT_SUFFIX = re.compile(
    r"\s*(ml|l|g|mg|kg|mol|m|n|cm3|dm3|ohm|s|min|k|c|°c|%)\.?$", re.IGNORECASE
)
_NUMERIC = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")


class ExtractionError(ValueError):
    pass


@dataclass
class ExtractionResult:
    values: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_number(raw: Any, field_name: str) -> float:
    """Strict numeric parse. Raises rather than guessing at intent."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ExtractionError(f"'{field_name}' is empty")

    if isinstance(raw, bool):
        raise ExtractionError(f"'{field_name}' must be a number, not true/false")

    if isinstance(raw, (int, float)):
        value = float(raw)
        if not math.isfinite(value):
            raise ExtractionError(f"'{field_name}' is not a finite number")
        return value

    if not isinstance(raw, str):
        raise ExtractionError(f"'{field_name}' must be a number")

    text = raw.strip()
    stripped_units = _UNIT_SUFFIX.sub("", text).strip()
    if stripped_units != text and _NUMERIC.match(stripped_units):
        # A trailing unit is unambiguous, so it is safe to remove.
        text = stripped_units

    if text.count(",") and text.count("."):
        raise ExtractionError(
            f"'{field_name}' contains both a comma and a full stop ({raw!r}); "
            "enter the number using a full stop for the decimal point only"
        )
    if "," in text:
        raise ExtractionError(
            f"'{field_name}' contains a comma ({raw!r}); if that is a decimal "
            "point, enter it as a full stop"
        )
    if text.count(".") > 1:
        raise ExtractionError(
            f"'{field_name}' has more than one decimal point ({raw!r})"
        )
    if not _NUMERIC.match(text):
        raise ExtractionError(f"'{field_name}' is not a number ({raw!r})")

    value = float(text)
    if not math.isfinite(value):
        raise ExtractionError(f"'{field_name}' is not a finite number")
    return value


def parse_series(raw: Any, field_name: str, *, min_length: int = 1) -> list[float]:
    """Parse a list of readings. One bad entry fails the whole series."""
    if raw is None:
        raise ExtractionError(f"'{field_name}' is missing")
    if isinstance(raw, str):
        parts = [p for p in re.split(r"[\s,;]+", raw.strip()) if p]
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        raise ExtractionError(f"'{field_name}' must be a list of readings")

    if len(parts) < min_length:
        raise ExtractionError(
            f"'{field_name}' has {len(parts)} reading(s); at least {min_length} "
            "are needed"
        )
    return [parse_number(p, f"{field_name}[{i}]") for i, p in enumerate(parts)]


def extract_submission(
    payload: dict[str, Any],
    *,
    numeric_fields: tuple[str, ...] = (),
    series_fields: tuple[str, ...] = (),
    required: tuple[str, ...] = (),
    text_fields: tuple[str, ...] = ("remarks",),
) -> ExtractionResult:
    """Validate a raw submission payload against an experiment's field spec.

    Collects every error rather than stopping at the first, so a student
    fixes one form rather than discovering problems one at a time.
    """
    result = ExtractionResult()

    if not isinstance(payload, dict) or not payload:
        result.errors.append("The submission is empty")
        return result

    for name in required:
        if name not in payload or payload[name] in (None, ""):
            result.errors.append(f"'{name}' is required")

    for name in numeric_fields:
        if name not in payload:
            continue
        try:
            result.values[name] = parse_number(payload[name], name)
        except ExtractionError as exc:
            result.errors.append(str(exc))

    for name in series_fields:
        if name not in payload:
            continue
        try:
            result.values[name] = parse_series(payload[name], name)
        except ExtractionError as exc:
            result.errors.append(str(exc))

    for name in text_fields:
        value = payload.get(name)
        if isinstance(value, str):
            result.values[name] = value.strip()

    return result


__all__ = [
    "ExtractionError",
    "ExtractionResult",
    "extract_submission",
    "parse_number",
    "parse_series",
]
