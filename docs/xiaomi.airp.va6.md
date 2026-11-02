# Mijia Air Purifier 6 Pro (`xiaomi.airp.va6`)

Support follows the model customisation approach accepted for the Air Purifier 6
(`xiaomi.airp.mb5`) in [PR #2954](https://github.com/al-one/hass-xiaomi-miot/pull/2954).
The implementation uses the existing MIoT parser, converters, entities and
transport. It does not require a model-specific driver or a python-miio fork.
The local-model entry follows mb5's automatic routing convention. LAN support is
provisional until a physical device accepts local requests.

## Specification and entities

The fixtures preserve the full official MIoT definitions, including the original
English labels and factory/debug services:

- [Version 1](https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:air-purifier:0000A007:xiaomi-va6:1:0000D050)
- [Version 2](https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:air-purifier:0000A007:xiaomi-va6:2:0000D050)

Normal-use features are exposed through standard Home Assistant entities:

- Fan power, specification-defined modes and three manual speed levels.
- UV, screen power, buzzer, child lock and abnormal-particle alert switches.
- Screen brightness and favourite level selects; a filter-reset button.
- Temperature, humidity, air quality, PM1, PM2.5, PM10 and formaldehyde sensors.
- Filter life and time counters, favourite area, fault and target/measured RPM.

Configuration and diagnostic categories follow the mb5 customisation. Polling is
grouped at 21 seconds for operating settings, 61 seconds for readings, 121 seconds
for configuration switches, and 301 seconds for filter counters. Factory debug,
self-check coordination, raw HCHO data, sensor serial numbers, error counters and
heartbeat writes are excluded. Door, child-lock and particle events are not
reconstructed as polled binary sensor states.

## Differences from mb5

- The Pro has HCHO sensing and no anion property. HCHO is already in mg/m³.
- Target RPM is SIID 13 / PIID 3; measured RPM is PIID 4. The mb5 feedback property
  uses PIID 3, so the two models must not share raw coordinates.
- Favourite levels are 0–10. The official English specification gives both 0 and
  1 the label `0`. Duplicate enum labels are disambiguated using native values so
  every option remains reachable, including in cloud-only mode. Unique labels
  and distinct translations remain unchanged.
- Screen brightness is 0 Dim, 1 Normal and 2 Mid. Screen power is separate.
- The PM10 specification has no unit and an unusual 0–100 range. Its raw reading
  is exposed without copying mb5's unit override; its meaning needs device
  validation. The raw sensor has no density device class until a unit is supplied.
- V2 adds extended filter counters at SIID 4 / PIIDs 4 and 5. Both original and
  extended counters use hours and retain distinct converter/entity unique IDs.
  Unsupported-property responses are handled by the existing MIoT result path.

Mode 6 is labelled `None` in the official English specification and denotes the
manual gear mode in the model's translated documentation. Existing specification
translations may supply a clearer label. No operating mode or room coverage is
inferred from undocumented firmware behaviour.

## Validation and release compatibility

The tests use real MIoT specifications, converters and entity implementations,
with mocked local and cloud responses. They check the entity inventory,
categories, units, excluded properties, request coordinates, mode/speed values,
all favourite levels, brightness, filter reset and failed property results.
The existing mb5 tests remain regression coverage. No physical device has been
tested.

The upstream branch identifies itself as 1.1.5, but PR #2954 merged after the
`v1.1.5` tag. The four changed production files were also patched onto the exact
tagged release and passed 209 model/enum tests on Home Assistant 2025.6.0 and
2026.10.4. The upstream checkout passed its full 551-test suite on both HA versions,
including the mb5 tests. The mb5 PM10 regression case runs against upstream only,
because the tag predates that model's customisation. Deployment should retain the
installed files and hashes for rollback and apply only these changes.

Before claiming hardware support, confirm LAN/token access, model and firmware
identity, sensor readings against the app/display, every mode and manual/favourite
level, screen settings and all switches. Check whether speed changes require the
manual preset, and whether favourite changes require the favourite preset.
Confirm original/extended filter counters and unsupported-property behaviour on
the installed firmware. Test filter reset after a real replacement, then network
recovery and normal operation for 24–48 hours. Capture anonymised responses for
regression fixtures and a Home Assistant entity screenshot for upstream review.
