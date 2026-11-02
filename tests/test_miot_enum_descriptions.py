"""Enum descriptions must preserve the native value of every selectable option."""

import pytest

from custom_components.xiaomi_miot.core.miot_spec import MiotSpec


@pytest.fixture
def make_enum_property(hass):
    """Build a property without device customizations or transport dependencies."""
    def make(descriptions, *, translations=None):
        spec = MiotSpec(hass, {
            "type": "urn:miot-spec-v2:device:air-purifier:0000A007:test:1",
            "services": [{
                "iid": 9,
                "type": "urn:miot-spec-v2:service:air-purifier-favorite:000078B2:test:1",
                "properties": [{
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:fan-level:00000016:test:1",
                    "format": "uint8",
                    "access": ["read", "write"],
                    "value-list": [
                        {"value": value, "description": description}
                        for value, description in enumerate(descriptions)
                    ],
                }],
            }],
        }, translations={
            "en": {
                MiotSpec.spec_lang_key(9, piid=1, viid=value): description
                for value, description in enumerate(translations or [])
            },
        }, trans_options=True)
        return spec.get_property("air_purifier_favorite.fan_level")

    return make


def test_unique_descriptions_remain_unchanged(make_enum_property):
    prop = make_enum_property(["First", "Second", "Third"])

    assert prop.list_descriptions() == ["First", "Second", "Third"]
    assert [prop.list_description(value) for value in range(3)] == prop.list_descriptions()
    assert prop.list_value(None) == [0, 1, 2]
    assert prop.list_value("Second") == 1
    assert prop.list_value("second") == 1
    assert prop.list_value("missing") is None
    assert prop.list_description(99) is None


@pytest.mark.parametrize("fixture", ["xiaomi.airp.va6.json", "xiaomi.airp.va6-v1.json"])
def test_va6_favorite_values_round_trip(load_miot_spec, fixture):
    prop = load_miot_spec(fixture).get_property("air_purifier_favorite.fan_level")

    assert prop.list_descriptions() == [f"{value}: {0 if value == 1 else value}" for value in range(11)]
    assert prop.list_value(None) == list(range(11))
    for value in range(11):
        assert prop.list_value(prop.list_description(value)) == value
    # Preserve the old first-match behavior for ambiguous raw aliases.
    assert prop.list_value("0") == 0
    assert prop.list_value("1") is None
    for value in range(2, 11):
        assert prop.list_value(str(value)) == value


def test_generated_labels_take_precedence_over_raw_aliases(make_enum_property):
    prop = make_enum_property(["Same", "Same", "0: Same"])

    assert prop.list_descriptions() == ["0: Same", "1: Same", "2: 0: Same"]
    assert len(set(prop.list_descriptions())) == 3
    for value in range(3):
        assert prop.list_value(prop.list_description(value)) == value
    assert prop.list_value("Same") == 0


def test_distinct_translations_are_preserved(make_enum_property):
    prop = make_enum_property(["0", "0"], translations=["3–6 m²", "6–11 m²"])

    assert prop.list_descriptions() == ["3–6 m²", "6–11 m²"]
    assert prop.list_value("3–6 m²") == 0
    assert prop.list_value("6–11 m²") == 1
    assert prop.list_value("0") == 0


def test_unique_translations_preserve_legacy_alias_precedence(make_enum_property):
    prop = make_enum_property(["A", "B"], translations=["B", "A"])

    assert prop.list_descriptions() == ["B", "A"]
    assert prop.list_value("A") == 0
    assert prop.list_value("B") == 0


def test_duplicate_translations_preserve_labels_and_raw_aliases(make_enum_property):
    prop = make_enum_property(["First", "Second"], translations=["Coverage", "Coverage"])

    assert prop.list_descriptions() == ["0: Coverage", "1: Coverage"]
    assert prop.list_value("0: Coverage") == 0
    assert prop.list_value("1: Coverage") == 1
    assert prop.list_value("First") == 0
    assert prop.list_value("second") == 1
    assert prop.list_value("Coverage") == 0


def test_lower_options_remain_selectable(make_enum_property):
    prop = make_enum_property(["First", "Second"], translations=["Coverage", "Coverage"])

    assert prop.list_descriptions(lower=True) == ["0: coverage", "1: coverage"]
    assert prop.list_description(1, lower=True) == "1: coverage"
    assert prop.list_value("1: coverage") == 1


def test_lower_options_disambiguate_case_collisions(make_enum_property):
    prop = make_enum_property(["Low", "low"])

    assert prop.list_descriptions() == ["Low", "low"]
    assert prop.list_descriptions(lower=True) == ["0: low", "1: low"]
    assert prop.list_value("Low") == 0
    assert prop.list_value("low") == 0  # Existing raw lowercase aliases still take precedence.
    assert prop.list_value("0: low") == 0
    assert prop.list_value("1: low") == 1


def test_empty_description_fallback_is_preserved(make_enum_property):
    prop = make_enum_property(["", "Second"])

    assert prop.list_descriptions() == ["0", "Second"]
    assert prop.list_description(0) == ""
    assert prop.list_value("") == 0


def test_empty_fallback_collision_is_disambiguated(make_enum_property):
    prop = make_enum_property(["", "0"])

    assert prop.list_descriptions() == ["0: 0", "1: 0"]
    assert prop.list_value(prop.list_description(0)) == 0
    assert prop.list_value(prop.list_description(1)) == 1


def test_empty_enum_and_null_lookup_are_preserved(make_enum_property):
    prop = make_enum_property([])

    assert prop.list_descriptions() == []
    assert prop.list_description(None) == []
    assert prop.list_description(0) is None
    assert prop.list_value(None) == []
    assert prop.list_value("0") is None


@pytest.mark.parametrize("value_range,expected", [([0, 2, 1], ["0", "1", "2"]), ([0, 1, 0.5], ["0", "0.5", "1.0"])])
def test_numeric_range_behavior_is_unchanged(make_enum_property, value_range, expected):
    prop = make_enum_property([])
    prop.value_range = value_range

    assert prop.list_descriptions() == expected
    assert prop.list_description(None) == expected
    assert prop.list_description(1) == "1"
    assert prop.list_value("1") == 1
    assert prop.list_value("invalid") is None
