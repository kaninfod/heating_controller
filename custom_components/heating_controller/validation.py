"""Pure validation and resolution helpers for the Heating Controller.

This module deliberately has no Home Assistant imports so the rules can be
unit-tested without a running HA instance.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

WEEKDAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_MAX_TRANSITIONS = 6
_MIN_TEMPERATURE = 4.0
_MAX_TEMPERATURE = 35.0
_TEMPERATURE_STEP = 0.5


def weekday_name(value: datetime) -> str:
    """Return the lowercase English weekday name for a datetime."""
    return WEEKDAYS[value.weekday()]


def validate_day_type_schedule(schedule: str) -> str:
    """Validate and normalise a day-type schedule.

    The TRVZB accepts 1-6 transitions, each ``HH:MM/TEMP``. The first
    transition must be ``00:00``, times must be ascending, temperatures must
    be 4-35 °C in 0.5 °C steps.

    Returns the schedule with temperatures normalised (``18.0`` -> ``18``,
    ``18.50`` -> ``18.5``). Raises ``ValueError`` with a user-facing message.
    """
    parts = schedule.split()

    if not 1 <= len(parts) <= _MAX_TRANSITIONS:
        raise ValueError(
            f"Schedule must have between 1 and {_MAX_TRANSITIONS} components, "
            f"got {len(parts)}: {schedule}"
        )

    if not parts[0].startswith("00:00/"):
        raise ValueError(f"Schedule must start with '00:00/', got: {parts[0]}")

    previous_minutes = -1
    normalised: list[str] = []

    for index, part in enumerate(parts, start=1):
        if "/" not in part:
            raise ValueError(f"Component {index} is missing a temperature: {part}")

        time_part, temp_part = part.split("/", 1)

        if not _TIME_RE.match(time_part):
            raise ValueError(
                f"Component {index} has an invalid time '{time_part}'. "
                "Expected HH:MM between 00:00 and 23:59."
            )

        hours = int(time_part[:2])
        minutes = int(time_part[3:])
        total_minutes = hours * 60 + minutes

        if total_minutes <= previous_minutes:
            raise ValueError(
                f"Component {index} time '{time_part}' must be later than the "
                "previous transition."
            )
        previous_minutes = total_minutes

        try:
            temperature = float(temp_part)
        except ValueError:
            raise ValueError(
                f"Component {index} has an invalid temperature: {temp_part}"
            ) from None

        if not _MIN_TEMPERATURE <= temperature <= _MAX_TEMPERATURE:
            raise ValueError(
                f"Component {index} temperature {temperature:g} is outside "
                f"{_MIN_TEMPERATURE:g}-{_MAX_TEMPERATURE:g} °C."
            )

        if abs(temperature * 2 - round(temperature * 2)) > 1e-9:
            raise ValueError(
                f"Component {index} temperature {temperature:g} must be in "
                f"{_TEMPERATURE_STEP:g} °C steps."
            )

        normalised.append(f"{time_part}/{temperature:g}")

    return " ".join(normalised)


def resolve_effective_area_ids(
    configurations: Sequence[Any], all_area_ids: Iterable[str]
) -> list[list[str] | None]:
    """Resolve each configuration's effective area IDs.

    - an explicit list is returned as-is
    - an empty list is the catch-all for areas not mentioned elsewhere
    - an empty list with no mentioned areas means all areas (``None``)

    An empty catch-all remainder is returned as an empty list; callers should
    skip that configuration rather than treating it as "all areas".
    """
    all_ids = set(all_area_ids)
    mentioned: set[str] = set()

    for configuration in configurations:
        area_ids = configuration.area_ids or []
        mentioned.update(area_ids)

    resolved: list[list[str] | None] = []

    for configuration in configurations:
        area_ids = configuration.area_ids or []

        if area_ids:
            resolved.append(list(area_ids))
        elif mentioned:
            resolved.append(sorted(all_ids - mentioned))
        else:
            resolved.append(None)

    return resolved
