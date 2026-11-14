import pytest
from ossdex_core.licenses import KIND_NOTES, KINDS, ids_for, known_ids, license_kind


@pytest.mark.parametrize("value, kind", [
    ("MIT", "permissive"), ("mit", "permissive"), ("Apache-2.0", "permissive"),
    ("BSD-3-Clause", "permissive"), ("Unlicense", "permissive"),
    ("MPL-2.0", "weak_copyleft"), ("LGPL-3.0", "weak_copyleft"),
    ("GPL-3.0", "copyleft"), ("GPL-3.0-only", "copyleft"), ("GPL-2.0-or-later", "copyleft"),
    ("AGPL-3.0", "network_copyleft"), ("AGPL-3.0-only", "network_copyleft"),
    ("NOASSERTION", "other"), ("other", "other"), ("BUSL-1.1", "other"), ("SSPL-1.0", "other"),
    (None, "none"), ("", "none"),
])
def test_license_kind(value, kind):
    assert license_kind(value) == kind


def test_every_kind_has_a_note_and_the_listed_ones_have_ids():
    assert set(KIND_NOTES) == set(KINDS)
    for kind in ("permissive", "weak_copyleft", "copyleft", "network_copyleft"):
        assert ids_for(kind)
    assert "mit" in ids_for("permissive") and "gpl-3.0-only" in ids_for("copyleft")
    assert ids_for("other") == [] and ids_for("none") == []
    assert set(known_ids()) >= set(ids_for("permissive")) | set(ids_for("network_copyleft"))
