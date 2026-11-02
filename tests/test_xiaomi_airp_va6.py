"""Exercise the 6 Pro's official specifications through real MIoT entities."""

import logging
from types import SimpleNamespace
from unicodedata import normalize
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.fan import FanEntityFeature
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.setup import async_setup_component
from homeassistant.util.percentage import ordered_list_item_to_percentage

from custom_components.xiaomi_miot.button import ButtonEntity
from custom_components.xiaomi_miot.fan import FanEntity
from custom_components.xiaomi_miot.select import SelectEntity
from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.switch import SwitchEntity
from custom_components.xiaomi_miot.core.miot_local_devices import MIOT_LOCAL_MODELS

MODEL = "xiaomi.airp.va6"
SPEC_FILES = (f"{MODEL}.json", f"{MODEL}-v1.json")
ENTITY_CLASSES = {
    "button": ButtonEntity,
    "fan": FanEntity,
    "select": SelectEntity,
    "sensor": SensorEntity,
    "switch": SwitchEntity,
}


@pytest.fixture(params=SPEC_FILES, ids=("v2", "v1"))
def device(request, make_device, load_miot_spec):
    return make_device(load_miot_spec(request.param), model=MODEL)


def converter_at(device, domain, siid, piid):
    matches = [
        conv for conv in device.converters
        if conv.domain == domain
        and getattr(conv, "prop", None)
        and (conv.prop.siid, conv.prop.iid) == (siid, piid)
    ]
    assert len(matches) == 1, (domain, siid, piid, matches)
    return matches[0]


def entity_at(device, domain, siid, piid):
    return ENTITY_CLASSES[domain](device, converter_at(device, domain, siid, piid))


def reply(siid, piid, value, code=0):
    return {"did": "test-device", "siid": siid, "piid": piid, "code": code, "value": value}


@pytest.fixture(params=("local", "cloud"))
def transport(request, device):
    """Replace only LAN/cloud I/O, preserving Device read/write and converters."""
    mode = request.param
    config = {"username": "test-user", "conn_mode": mode}
    device.entry.get_config = lambda key=None, default=None: config.get(key, default)
    # The tagged runtime requires a successful initial poll before local writes.
    device._local_state = mode == "local"

    def set_properties(params):
        return [{**param, "code": 0} for param in params]

    def send(method, params):
        if method == "set_properties":
            return set_properties(params)
        assert method == "action"
        return {**params, "code": 0, "out": []}

    device.local = SimpleNamespace(
        async_send=AsyncMock(side_effect=send),
        async_get_properties_for_mapping=AsyncMock(),
    )
    device.cloud = SimpleNamespace(
        user_id="test-user",
        async_set_props=AsyncMock(side_effect=set_properties),
        async_do_action=AsyncMock(side_effect=lambda params: {**params, "code": 0, "out": []}),
        async_get_properties_for_mapping=AsyncMock(),
    )
    return SimpleNamespace(device=device, mode=mode)


def assert_write(transport, siid, piid, value):
    device = transport.device
    expected = [{"did": device.did, "siid": siid, "piid": piid, "value": value}]
    if transport.mode == "local":
        device.local.async_send.assert_awaited_once_with("set_properties", expected)
        device.cloud.async_set_props.assert_not_awaited()
    else:
        device.cloud.async_set_props.assert_awaited_once_with(expected)
        device.local.async_send.assert_not_awaited()


def test_local_miot_allowlist():
    assert MODEL in MIOT_LOCAL_MODELS


def test_supported_normal_entities(device):
    names = {conv.full_name for conv in device.converters if conv.domain}
    assert {
        "fan.air_purifier.on",
        "switch.air_purifier.uv",
        "switch.screen.on",
        "switch.alarm",
        "switch.physical_controls_locked",
        "select.screen.brightness",
        "select.air_purifier_favorite.fan_level",
        "button.filter.reset_filter_life",
        "sensor.environment.pm1",
    } <= names
    for domain, siid, piid in [
        ("sensor", 2, 2), ("sensor", 3, 1), ("sensor", 3, 3),
        ("sensor", 3, 4), ("sensor", 3, 5), ("sensor", 3, 7),
        ("sensor", 3, 9), ("sensor", 3, 11), ("sensor", 4, 1),
        ("sensor", 4, 2), ("sensor", 4, 3), ("sensor", 13, 1),
        ("sensor", 13, 3), ("sensor", 13, 4), ("switch", 13, 12),
    ]:
        converter_at(device, domain, siid, piid)


def test_factory_properties_are_not_polled_or_exposed(device):
    mapping = device.miot_mapping()
    coordinates = {(value["siid"], value["piid"]) for value in mapping.values()}
    excluded = {
        (10, 1), (10, 2), (10, 3), (12, 1),
        (13, 2), (13, 5), (13, 6), (13, 7), (13, 10), (13, 11),
        (14, 1), (14, 2), (14, 3),
    }
    assert not coordinates & excluded
    assert {(13, 1), (13, 3), (13, 4), (13, 12)} <= coordinates
    for conv in device.converters:
        prop = getattr(conv, "prop", None)
        action = getattr(conv, "action", None)
        assert not prop or (prop.siid, prop.iid) not in excluded
        assert not prop or prop.siid not in {10, 12, 14}
        assert not action or action.siid not in {10, 12, 13, 14}
        assert "anion" not in conv.full_name
        assert "rfid" not in conv.full_name


def test_entity_categories(device):
    for domain, siid, piid in [
        ("switch", 2, 7), ("switch", 7, 1), ("switch", 6, 1),
        ("switch", 8, 1), ("switch", 13, 12),
        ("select", 7, 2), ("select", 9, 1),
    ]:
        assert entity_at(device, domain, siid, piid).entity_category is EntityCategory.CONFIG
    reset = ButtonEntity(device, device.find_converter("button.filter.reset_filter_life"))
    assert reset.entity_category is EntityCategory.CONFIG
    for siid, piid in [(2, 2), (13, 3), (13, 4)]:
        assert entity_at(device, "sensor", siid, piid).entity_category is EntityCategory.DIAGNOSTIC
    assert entity_at(device, "fan", 2, 1).entity_category is None
    for piid in (1, 3, 4, 5, 7, 9, 11):
        assert entity_at(device, "sensor", 3, piid).entity_category is None


@pytest.mark.parametrize("siid,piid,value,unit", [
    (3, 1, 47, "%"), (3, 7, 24.6, "°C"),
    (3, 4, 12, "μg/m³"), (3, 5, 8, None),
    (3, 9, 5, "μg/m³"), (3, 11, 0.023, "mg/m³"),
    (4, 1, 89, "%"), (4, 2, 1800, "hours"), (4, 3, 240, "hours"),
    (13, 3, 1200, "rpm"), (13, 4, 1174, "rpm"),
    (13, 1, "33-58", None),
])
def test_sensor_values_and_units(device, siid, piid, value, unit):
    sensor = entity_at(device, "sensor", siid, piid)
    sensor.set_state(device.decode(reply(siid, piid, value)))
    assert sensor.native_value == value
    observed_unit = sensor.native_unit_of_measurement
    if isinstance(unit, str):
        assert isinstance(observed_unit, str)
        assert normalize("NFKC", observed_unit) == normalize("NFKC", unit)
    else:
        assert observed_unit == unit


async def test_unitless_pm10_publishes_raw_state_without_invalid_unit_warning(device, hass, caplog):
    sensor = entity_at(device, "sensor", 3, 5)
    device.dispatch(device.decode(reply(3, 5, 8)))
    assert sensor.native_unit_of_measurement is None
    assert sensor.device_class is None
    assert sensor.native_value == 8

    assert await async_setup_component(hass, "sensor", {})
    with caplog.at_level(logging.WARNING, logger="homeassistant.components.sensor"):
        await hass.data["sensor"].async_add_entities([sensor])
        await hass.async_block_till_done()
        assert sensor.state == 8
    assert hass.states.get(sensor.entity_id).state == "8"
    assert "is not a valid unit for the device class" not in caplog.text


async def test_mb5_explicit_pm10_unit_preserves_density_metadata(make_device, load_miot_spec, hass):
    device = make_device(load_miot_spec("xiaomi.airp.mb5.json"), model="xiaomi.airp.mb5")
    sensor = entity_at(device, "sensor", 3, 5)
    device.dispatch(device.decode(reply(3, 5, 8)))
    assert sensor.device_class is SensorDeviceClass.PM10
    assert normalize("NFKC", sensor.native_unit_of_measurement) == normalize("NFKC", "μg/m³")
    assert sensor.native_value == 8

    assert await async_setup_component(hass, "sensor", {})
    await hass.data["sensor"].async_add_entities([sensor])
    await hass.async_block_till_done()
    assert sensor.state == 8
    assert hass.states.get(sensor.entity_id).state == "8"


def test_filter_versions_have_distinct_sensor_identity(device):
    converters = [
        conv for conv in device.converters
        if conv.domain == "sensor"
        and getattr(conv, "prop", None)
        and conv.prop.siid == 4
        and conv.prop.name in {"filter_left_time", "filter_used_time"}
    ]
    expected = {2, 3, 4, 5} if ":xiaomi-va6:2:" in device.spec.type else {2, 3}
    assert {conv.prop.iid for conv in converters} == expected
    sensors = [SensorEntity(device, conv) for conv in converters]
    assert len({conv.full_name for conv in converters}) == len(converters)
    assert len({sensor.unique_id for sensor in sensors}) == len(sensors)
    assert all(sensor.native_unit_of_measurement == "hours" for sensor in sensors)
    for sensor in sensors:
        value = 12000 if sensor.conv.prop.iid > 3 else 1200
        sensor.set_state(device.decode(reply(4, sensor.conv.prop.iid, value)))
        assert sensor.native_value == value


@pytest.mark.parametrize("siid,piid,wire,description", [
    (2, 2, 0, "no faults"), (2, 2, 3, "hcho error"),
    (3, 3, 0, "excellent"), (3, 3, 4, "heavy pollution"),
])
def test_fault_and_air_quality_descriptions(device, siid, piid, wire, description):
    sensor = entity_at(device, "sensor", siid, piid)
    sensor.set_state(device.decode(reply(siid, piid, wire)))
    assert sensor.native_value == description


@pytest.mark.parametrize("wire,label", [(0, "Auto"), (3, "Sleep"), (5, "Favorite"), (6, "None")])
async def test_fan_modes_use_native_wire_values(transport, wire, label):
    fan = entity_at(transport.device, "fan", 2, 1)
    assert fan.preset_modes == ["Auto", "Sleep", "Favorite", "None"]
    fan.set_state(transport.device.decode([reply(2, 1, True), reply(2, 4, wire)]))
    assert fan.preset_mode == label
    await fan.async_set_preset_mode(label)
    assert_write(transport, 2, 4, wire)


@pytest.mark.parametrize("wire,label", [(0, "Level1"), (1, "Level2"), (2, "Level3")])
async def test_fan_levels_use_native_zero_based_values(transport, wire, label):
    fan = entity_at(transport.device, "fan", 2, 1)
    assert fan.speed_count == 3
    assert fan.supported_features & FanEntityFeature.SET_SPEED
    fan.set_state(transport.device.decode([reply(2, 1, True), reply(2, 5, wire)]))
    percentage = ordered_list_item_to_percentage(["Level1", "Level2", "Level3"], label)
    assert fan.percentage == percentage
    await fan.async_set_percentage(percentage)
    assert_write(transport, 2, 5, wire)


async def test_fan_power_and_preset_are_written_together(transport):
    device = transport.device
    fan = entity_at(device, "fan", 2, 1)
    fan.set_state(device.decode(reply(2, 1, False)))
    with patch("custom_components.xiaomi_miot.fan.async_call_later"):
        await fan.async_turn_on(preset_mode="Sleep")
    expected = [
        {"did": device.did, "siid": 2, "piid": 1, "value": True},
        {"did": device.did, "siid": 2, "piid": 4, "value": 3},
    ]
    if transport.mode == "local":
        device.local.async_send.assert_awaited_once_with("set_properties", expected)
    else:
        device.cloud.async_set_props.assert_awaited_once_with(expected)


async def test_fan_power_off_does_not_write_mode_or_speed(transport):
    fan = entity_at(transport.device, "fan", 2, 1)
    await fan.async_turn_off()
    assert_write(transport, 2, 1, False)


@pytest.mark.parametrize("wire,label", [(0, "Dim"), (1, "Normal"), (2, "Mid")])
async def test_brightness_is_independent_of_screen_power(transport, wire, label):
    device = transport.device
    brightness = entity_at(device, "select", 7, 2)
    screen = entity_at(device, "switch", 7, 1)
    decoded = device.decode([reply(7, 1, True), reply(7, 2, wire)])
    brightness.set_state(decoded)
    screen.set_state(decoded)
    assert brightness.options == ["Dim", "Normal", "Mid"]
    assert brightness.current_option == label
    assert screen.is_on is True
    await brightness.async_select_option(label)
    assert_write(transport, 7, 2, wire)
    assert screen.is_on is True


@pytest.mark.parametrize("wire", range(11))
async def test_every_favorite_level_round_trips_including_duplicate_label(transport, wire):
    device = transport.device
    favorite = entity_at(device, "select", 9, 1)
    assert len(favorite.options) == len(set(favorite.options)) == 11
    prop = favorite.conv.prop
    option = prop.list_description(wire)
    assert prop.list_value(option) == wire
    favorite.set_state(device.decode(reply(9, 1, wire)))
    assert favorite.current_option == option
    await favorite.async_select_option(option)
    assert_write(transport, 9, 1, wire)


@pytest.mark.parametrize("siid,piid", [(2, 7), (7, 1), (6, 1), (8, 1), (13, 12)])
@pytest.mark.parametrize("enabled", (False, True))
async def test_switches_read_and_write_exact_properties(transport, siid, piid, enabled):
    switch = entity_at(transport.device, "switch", siid, piid)
    switch.set_state(transport.device.decode(reply(siid, piid, enabled)))
    assert switch.is_on is enabled
    if enabled:
        await switch.async_turn_on()
    else:
        await switch.async_turn_off()
    assert_write(transport, siid, piid, enabled)


async def test_filter_reset_uses_documented_action(transport):
    device = transport.device
    button = ButtonEntity(device, device.find_converter("button.filter.reset_filter_life"))
    await button.async_press()
    expected = {"did": device.did, "siid": 4, "aiid": 1, "in": []}
    if transport.mode == "local":
        device.local.async_send.assert_awaited_once_with("action", expected)
        device.cloud.async_do_action.assert_not_awaited()
    else:
        device.cloud.async_do_action.assert_awaited_once_with(expected)
        device.local.async_send.assert_not_awaited()


async def test_mocked_property_reads_update_real_entities(transport):
    device = transport.device
    humidity = entity_at(device, "sensor", 3, 1)
    hcho = entity_at(device, "sensor", 3, 11)
    readings = [reply(3, 11, 0.023), reply(3, 1, 47)]
    device.local.async_get_properties_for_mapping.return_value = readings
    device.cloud.async_get_properties_for_mapping.return_value = readings
    mapping = {
        humidity.conv.prop.full_name: {"siid": 3, "piid": 1},
        hcho.conv.prop.full_name: {"siid": 3, "piid": 11},
    }
    await device.async_get_properties(mapping)
    assert humidity.native_value == 47
    assert hcho.native_value == 0.023
    if transport.mode == "local":
        device.local.async_get_properties_for_mapping.assert_awaited_once_with(did=device.did, mapping=mapping)
        device.cloud.async_get_properties_for_mapping.assert_not_awaited()
    else:
        device.cloud.async_get_properties_for_mapping.assert_awaited_once_with(device.did, mapping)
        device.local.async_get_properties_for_mapping.assert_not_awaited()


async def test_failed_property_response_does_not_overwrite_sensor(transport):
    device = transport.device
    hcho = entity_at(device, "sensor", 3, 11)
    hcho.set_state(device.decode(reply(3, 11, 0.023)))
    readings = [reply(3, 11, 0.9, code=-4004)]
    device.local.async_get_properties_for_mapping.return_value = readings
    device.cloud.async_get_properties_for_mapping.return_value = readings
    await device.async_get_properties({hcho.conv.prop.full_name: {"siid": 3, "piid": 11}})
    assert hcho.native_value == 0.023


async def test_optional_extended_filter_failures_preserve_standard_readings(transport):
    device = transport.device
    humidity = entity_at(device, "sensor", 3, 1)
    left = entity_at(device, "sensor", 4, 2)
    readings = [reply(3, 1, 47), reply(4, 2, 1800)]
    if ":xiaomi-va6:2:" in device.spec.type:
        readings.extend([reply(4, 4, None, code=-4004), reply(4, 5, None, code=-4004)])
    device.local.async_get_properties_for_mapping.return_value = readings
    device.cloud.async_get_properties_for_mapping.return_value = readings
    await device.async_get_properties(device.miot_mapping())
    assert humidity.native_value == 47
    assert left.native_value == 1800


async def test_failed_write_does_not_dispatch_optimistic_switch_state(transport):
    device = transport.device
    switch = entity_at(device, "switch", 2, 7)
    switch.set_state(device.decode(reply(2, 7, False)))
    if transport.mode == "local":
        device.local.async_send.side_effect = None
        device.local.async_send.return_value = [reply(2, 7, True, code=-4004)]
    else:
        device.cloud.async_set_props.side_effect = None
        device.cloud.async_set_props.return_value = [reply(2, 7, True, code=-4004)]
    await switch.async_turn_on()
    assert switch.is_on is False
