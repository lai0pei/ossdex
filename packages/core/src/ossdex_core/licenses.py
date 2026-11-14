"""What a license lets you do, in five kinds.

The stored `license` is GitHub's SPDX id (or its key when it has no SPDX id). This maps it to a kind
so a client can ask for "permissive only" and the model can explain the consequences. It is a summary
for orientation, not legal advice: the repo's LICENSE file is what counts.
"""

from __future__ import annotations

from typing import Literal

LicenseKind = Literal["permissive", "weak_copyleft", "copyleft", "network_copyleft", "other", "none"]
KINDS: tuple[str, ...] = ("permissive", "weak_copyleft", "copyleft", "network_copyleft", "other",
                          "none")

_BASE: dict[str, tuple[str, ...]] = {
    "permissive": (
        "mit", "mit-0", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "bsd-3-clause-clear",
        "bsd-4-clause", "isc", "0bsd", "unlicense", "zlib", "bsl-1.0", "cc0-1.0", "postgresql",
        "upl-1.0", "python-2.0", "wtfpl", "ncsa", "artistic-2.0", "afl-3.0", "blueoak-1.0.0",
        "ms-pl", "curl", "libpng", "x11",
    ),
    "weak_copyleft": (
        "lgpl-2.0", "lgpl-2.1", "lgpl-3.0", "mpl-2.0", "epl-1.0", "epl-2.0", "cddl-1.0",
        "osl-3.0", "eupl-1.1", "eupl-1.2", "ms-rl",
    ),
    "copyleft": ("gpl-2.0", "gpl-3.0"),
    "network_copyleft": ("agpl-3.0",),
}
_SUFFIXES = ("-only", "-or-later", "+")

KIND_NOTES: dict[str, str] = {
    "permissive": "Use it in closed, commercial and hosted products; keep the copyright and license "
                  "notice. The safest base for a product or client work.",
    "weak_copyleft": "Usable in commercial products. Changes to the licensed files (or the library "
                     "itself) must be shared, but your own code around it can stay closed.",
    "copyleft": "Fine to run as a hosted service, but if you distribute software built on it you "
                "must release your source under the same license. Not suited to closed products.",
    "network_copyleft": "Like GPL, and also covers hosted use: if users reach a modified version over "
                        "a network (SaaS), you must offer them your source. Risky as a closed SaaS base.",
    "other": "GitHub could not classify the license. It may be source-available (BSL, SSPL, Elastic, "
             "fair-code) with commercial limits, or custom terms. Read the LICENSE file before use.",
    "none": "No license: all rights reserved. Not open source; you may not reuse the code without "
            "the author's permission.",
}


def _variants(ids: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for i in ids:
        out.append(i)
        if i.startswith(("gpl-", "lgpl-", "agpl-")):
            out += [i + s for s in _SUFFIXES]
    return out


_IDS: dict[str, list[str]] = {k: _variants(v) for k, v in _BASE.items()}
_LOOKUP: dict[str, str] = {i: k for k, ids in _IDS.items() for i in ids}


def license_kind(value: str | None) -> str:
    """The kind of a stored license value (case-insensitive)."""
    if not value:
        return "none"
    return _LOOKUP.get(value.strip().lower(), "other")


def ids_for(kind: str) -> list[str]:
    """Lowercase license ids of a kind (variants included); `other` and `none` have no list."""
    return list(_IDS.get(kind, []))


def known_ids() -> list[str]:
    return list(_LOOKUP)
