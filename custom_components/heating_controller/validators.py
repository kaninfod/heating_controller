"""Configuration validators for Heating Controller."""

from __future__ import annotations

import logging
from typing import Any

from .const import HARD_MODES

_LOGGER = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Configuration validation error."""

    pass


def validate_pseudo_modes(
    pseudo_modes_config: list[dict[str, Any]], areas_config: list[dict[str, Any]]
) -> None:
    """Validate pseudo modes configuration.

    Args:
        pseudo_modes_config: List of pseudo mode configurations
        areas_config: List of area configurations

    Raises:
        ConfigValidationError: If configuration is invalid
    """
    # Build set of valid area IDs
    valid_area_ids = {area["id"] for area in areas_config}

    for pm_config in pseudo_modes_config:
        pm_name = pm_config.get("name", "Unknown")

        # Support both old (parent_mode + area_ids) and new (configurations) formats
        if "configurations" in pm_config:
            configurations = pm_config["configurations"]

            if not isinstance(configurations, list) or len(configurations) == 0:
                raise ConfigValidationError(
                    f"Pseudo mode '{pm_name}': 'configurations' must be a non-empty list"
                )

            # Track area_ids across all configurations to detect duplicates
            all_area_ids_in_mode: list[str] = []
            empty_area_ids_count = 0  # Track how many configs have empty area_ids

            for i, config in enumerate(configurations):
                if not isinstance(config, dict):
                    raise ConfigValidationError(
                        f"Pseudo mode '{pm_name}': configuration {i} must be a dict"
                    )

                # Validate parent_mode
                parent_mode = config.get("parent_mode")
                if not parent_mode:
                    raise ConfigValidationError(
                        f"Pseudo mode '{pm_name}' configuration {i}: "
                        "'parent_mode' is required"
                    )

                if parent_mode not in HARD_MODES:
                    raise ConfigValidationError(
                        f"Pseudo mode '{pm_name}' configuration {i}: "
                        f"parent_mode '{parent_mode}' is not valid. "
                        f"Valid modes: {', '.join(HARD_MODES)}"
                    )

                # Validate area_ids
                area_ids = config.get("area_ids", [])
                if not isinstance(area_ids, list):
                    raise ConfigValidationError(
                        f"Pseudo mode '{pm_name}' configuration {i}: "
                        "'area_ids' must be a list"
                    )

                # If area_ids is empty, it's a catch-all for unmentioned areas
                if len(area_ids) == 0:
                    empty_area_ids_count += 1
                    if empty_area_ids_count > 1:
                        raise ConfigValidationError(
                            f"Pseudo mode '{pm_name}': "
                            "only one configuration can have empty area_ids (catch-all). "
                            f"Found {empty_area_ids_count} configurations with empty area_ids"
                        )
                    _LOGGER.debug(
                        f"Pseudo mode '{pm_name}' configuration {i}: "
                        "area_ids is empty, will apply to unmentioned areas (catch-all)"
                    )
                else:
                    # Validate each area_id exists
                    for area_id in area_ids:
                        if area_id not in valid_area_ids:
                            raise ConfigValidationError(
                                f"Pseudo mode '{pm_name}' configuration {i}: "
                                f"area_id '{area_id}' is not defined in areas config. "
                                f"Valid areas: {', '.join(sorted(valid_area_ids))}"
                            )

                        # Check for duplicates within this pseudo_mode
                        if area_id in all_area_ids_in_mode:
                            raise ConfigValidationError(
                                f"Pseudo mode '{pm_name}': "
                                f"area_id '{area_id}' appears in multiple configurations"
                            )

                    all_area_ids_in_mode.extend(area_ids)

        elif "parent_mode" in pm_config:
            # Old format support (single config)
            parent_mode = pm_config.get("parent_mode")

            if parent_mode not in HARD_MODES:
                raise ConfigValidationError(
                    f"Pseudo mode '{pm_name}': "
                    f"parent_mode '{parent_mode}' is not valid. "
                    f"Valid modes: {', '.join(HARD_MODES)}"
                )

            area_ids = pm_config.get("area_ids", [])
            if not isinstance(area_ids, list):
                raise ConfigValidationError(
                    f"Pseudo mode '{pm_name}': 'area_ids' must be a list"
                )

            for area_id in area_ids:
                if area_id not in valid_area_ids:
                    raise ConfigValidationError(
                        f"Pseudo mode '{pm_name}': "
                        f"area_id '{area_id}' is not defined in areas config. "
                        f"Valid areas: {', '.join(sorted(valid_area_ids))}"
                    )
        else:
            raise ConfigValidationError(
                f"Pseudo mode '{pm_name}': "
                "must have either 'configurations' or 'parent_mode' + 'area_ids'"
            )
