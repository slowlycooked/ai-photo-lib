from __future__ import annotations

from app.services.tag_localization import expand_term_aliases, to_chinese_tag


def test_to_chinese_tag_prefers_chinese_canonical_value() -> None:
    assert to_chinese_tag("boating") == "划船"
    assert to_chinese_tag("night") == "夜晚"
    assert to_chinese_tag("outdoor") == "户外"


def test_expand_term_aliases_contains_cross_language_aliases() -> None:
    aliases = expand_term_aliases("划船")
    assert "划船" in aliases
    assert "boating" in aliases

    aliases = expand_term_aliases("boating")
    assert "划船" in aliases
    assert "boating" in aliases
