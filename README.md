# Heating Controller

A Home Assistant custom integration for room-by-room heating control with Zigbee2MQTT radiator thermostats (TRVZB-style devices).

You define **areas**, reusable **day types**, weekly **schedules**, and named **heating modes** in YAML. The integration calculates a weekly schedule and publishes it to each thermostat over MQTT.

## Features

- Multi-zone heating with one or more thermostats per area.
- Reusable temperature curves (`day_types`) and weekly compositions (`schedules`).
- Named heating modes built from one or more `parent_mode` + `area_ids` slices.
- Area-specific modes, e.g. "bedroom on the weekend curve, everything else on the normal week".
- MQTT output to `<mqtt_topic_base>/<mqtt_name>/set` using Zigbee2MQTT device names.
- Restores the selected mode after a Home Assistant restart.
- `select.previous_heating_mode` helper entity.
- YAML configuration only (no config flow).

## Requirements

- Home Assistant with the **MQTT** integration configured.
- Zigbee2MQTT managing the thermostats.
- Thermostat firmware that accepts the flattened `weekly_schedule_<day>` payload keys.
- The thermostats paired and named in Zigbee2MQTT exactly as their `mqtt_name` in the config.

## Installation

### HACS (custom repository)

1. Open HACS → Integrations → ⋮ → **Custom repositories**.
2. Add `https://github.com/kaninfod/heating_controller` as an **Integration**.
3. Install **Heating Controller**.
4. Restart Home Assistant.

### Manual

Copy the integration folder into your Home Assistant config:

```text
config/
└── custom_components/
    └── heating_controller/
        ├── __init__.py
        ├── const.py
        ├── manifest.json
        ├── models.py
        ├── mqtt_handler.py
        ├── schedule_manager.py
        ├── select.py
        ├── strings.json
        └── validators.py
```

Restart Home Assistant after copying.

## Configuration

Add a `heating_controller:` block to `configuration.yaml`, then restart or reload YAML.

A complete example is in [`examples/configuration.yaml`](examples/configuration.yaml).

```yaml
heating_controller:
  mqtt_topic_base: "zigbee2mqtt"

  areas:
    - name: Bedroom
      id: bedroom
      thermostats:
        - climate_entity: climate.bedroom_thermostat
          mqtt_name: "bedroom thermostat"

    - name: Kitchen
      id: kitchen
      thermostats:
        - climate_entity: climate.kitchen_thermostat
          mqtt_name: "kitchen thermostat"

  day_types:
    workday: "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18"
    weekend: "00:00/18.5 06:30/20 09:00/20 17:00/20 22:00/20 23:00/18"
    eco: "00:00/18.5 07:00/18.5 09:00/18.5 17:00/18.5 22:00/18.5 23:00/18.5"

  schedules:
    default:
      monday: workday
      tuesday: workday
      wednesday: workday
      thursday: workday
      friday: workday
      saturday: weekend
      sunday: weekend
    eco:
      monday: eco
      tuesday: eco
      wednesday: eco
      thursday: eco
      friday: eco
      saturday: eco
      sunday: eco

  heating_modes:
    - name: "Normal mode"
      configurations:
        - parent_mode: "default"
          area_ids: []

    - name: "Stay home"
      configurations:
        - parent_mode: "stay_home"
          area_ids: []

    - name: "Stay home (bedroom only)"
      configurations:
        - parent_mode: "stay_home"
          area_ids: [bedroom]
        - parent_mode: "default"
          area_ids: []

    - name: "Eco mode"
      configurations:
        - parent_mode: "eco"
          area_ids: []

    - name: "Heating Off"
      configurations:
        - parent_mode: "heating_off"
          area_ids: []
```

### `areas`

Each area has a display `name`, a stable `id` (used by `area_ids`), and one or more thermostats:

- `climate_entity` — the Home Assistant climate entity.
- `mqtt_name` — the Zigbee2MQTT device name, used in the MQTT topic.

### `day_types`

A named temperature curve. The format is:

```text
HH:MM/TEMP HH:MM/TEMP HH:MM/TEMP HH:MM/TEMP HH:MM/TEMP HH:MM/TEMP
```

Exactly **6** components are required, and the first must be `00:00/...`.

### `schedules`

Maps a schedule name to the day type for each weekday:

```yaml
default:
  monday: workday
  ...
  saturday: weekend
  sunday: weekend
```

`default` and `eco` are the schedule names used by the corresponding hard modes.

### `heating_modes` and `parent_mode`

A heating mode is a user-facing name for one or more **configurations**. Each configuration applies a `parent_mode` to a set of areas:

```yaml
heating_modes:
  - name: "Custom mode"
    configurations:
      - parent_mode: stay_home
        area_ids: [bedroom]
      - parent_mode: default
        area_ids: []
```

`parent_mode` is the underlying hard mode. It is **not** inheritance and it is **not** a schedule name.

| `parent_mode` | HVAC sent | Schedule | Meaning |
|---|---|---|---|
| `default` | `auto` | `schedules.default` | Normal week. |
| `stay_home` | `auto` | `schedules.default`, with **today** replaced by the `weekend` day type | Home today, without changing the rest of the week. |
| `eco` | `auto` | `schedules.eco` | Energy-saving week. |
| `manual` | `heat` | none | Thermostat runs in local/manual mode. |
| `heating_off` | `off` | none | Heating off. |

`stay_home` requires a day type literally named `weekend` in `day_types`.

#### How `area_ids` resolves

- A non-empty list applies that `parent_mode` to exactly those areas.
- An empty list `[]` is a **catch-all for unmentioned areas** when at least one other configuration in the same mode mentions areas.
- An empty list with no mentioned areas applies to **all areas**.
- Only one catch-all configuration is allowed per mode.
- An area ID may not appear in more than one explicit configuration.

## Entities

After setup you get:

- `select.heating_mode` — the main mode selector. Its options are the `name` values from `heating_modes`.
- `select.previous_heating_mode` — tracks the previously selected mode.

The main selector restores its last option after a Home Assistant restart.

## Example: working from home in the bedroom

```yaml
- name: "Stay home (bedroom only)"
  configurations:
    - parent_mode: "stay_home"
      area_ids: [bedroom]
    - parent_mode: "default"
      area_ids: []
```

On a weekday this produces:

| Area | Today's curve | 09:00–17:00 |
|---|---|---|
| Bedroom | `weekend` | 20 °C |
| All other areas | `workday` | 18.5 °C |

The bedroom stays warm through the working day; the rest of the apartment follows the normal weekday setback. The second configuration is important: it forces the other areas back to `default`. Without it, unmentioned areas keep whatever mode they were previously in.

`stay_home` only overrides **today**. If you work from home on several days, select the mode again each morning or trigger it from an automation:

```yaml
service: select.select_option
target:
  entity_id: select.heating_mode
data:
  option: "Stay home (bedroom only)"
```

## MQTT payload

Topic:

```text
<mqtt_topic_base>/<mqtt_name>/set
```

Example:

```text
zigbee2mqtt/bedroom thermostat/set
```

Payload for a scheduled mode:

```json
{
  "system_mode": "auto",
  "weekly_schedule_monday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
  "weekly_schedule_tuesday": "...",
  "weekly_schedule_wednesday": "...",
  "weekly_schedule_thursday": "...",
  "weekly_schedule_friday": "...",
  "weekly_schedule_saturday": "...",
  "weekly_schedule_sunday": "..."
}
```

For `manual` and `heating_off`, only `system_mode` is sent.

## Known limitations

- **Ventilation is not implemented.** `ventilation_time_minutes` is parsed but unused, `parent_mode: ventilation` is not a valid hard mode, and no `ventilate_for_duration` service is registered.
- **`valve_opening_degree` is parsed but not published.** The payload line in `mqtt_handler.py` is currently commented out.
- **`default_mode` is not read.** It is accepted as extra config but has no effect.
- **`stay_home` is a today-only override.** It does not persist across weekdays.
- **YAML only.** There is no config flow; `config_flow` is `false`.
- **No per-area permanent schedule.** Areas follow the schedule of the selected mode; there is no per-area schedule assignment.

## Troubleshooting

### The select has no options

- Check that the block is under `heating_controller:` in `configuration.yaml`.
- Check the Home Assistant log for `Configuration validation error`.
- Ensure `heating_modes` is used, not the old `pseudo_modes` key.
- Ensure every `parent_mode` is one of `default`, `stay_home`, `eco`, `manual`, `heating_off`.

### `stay_home` does not change anything

- Ensure `day_types` contains an entry named exactly `weekend`.
- Ensure `schedules.default` exists.
- Check the log for `Day type 'weekend' not found` or `Mode 'default' not found`.

### Thermostats do not update

- Confirm the MQTT integration is loaded.
- Confirm each `mqtt_name` matches the Zigbee2MQTT device name exactly.
- Watch the log for `Publishing to ...` and `Failed to publish ...`.

### Wrong daytime temperature

- Check the `workday` / `weekend` `day_types` values.
- Remember that `stay_home` replaces only **today** with the `weekend` curve.

## Development

```bash
python -m pip install -r requirements_test.txt
python -m pytest -q
```

The integration lives in `custom_components/heating_controller/`. The tests are in `tests/`.

## License

No license file is currently included.
