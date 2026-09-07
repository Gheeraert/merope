"""SPDX resolution for the small set of licenses relevant to an academic
site (Creative Commons 4.0 and CC0), in the same spirit as the
companion project Mini-Métopes (C:/mini-metopes,
https://github.com/Gheeraert/mini-metopes,
src/mini_metopes/metadata/validation.py's SPDX_LICENSES).
"""

from __future__ import annotations

from dataclasses import dataclass

SPDX_LICENSES: dict[str, tuple[str, str]] = {
    "CC-BY-4.0": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "CC-BY-SA-4.0": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "CC-BY-ND-4.0": ("CC BY-ND 4.0", "https://creativecommons.org/licenses/by-nd/4.0/"),
    "CC-BY-NC-4.0": ("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
    "CC-BY-NC-SA-4.0": ("CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    "CC-BY-NC-ND-4.0": ("CC BY-NC-ND 4.0", "https://creativecommons.org/licenses/by-nc-nd/4.0/"),
    "CC0-1.0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
}


@dataclass(slots=True, frozen=True)
class ResolvedLicense:
    name: str | None
    url: str | None


def resolve_license(*, spdx_id: str | None, name: str | None, url: str | None) -> ResolvedLicense:
    """A known SPDX id (see SPDX_LICENSES) resolves to its canonical
    name/URL, overriding whatever free-text name/url was also given —
    it's the whole point of naming a known license by its SPDX id
    instead of typing it out. An unknown or absent spdx_id falls back
    to the free-text fields as given, so any other license remains
    representable without one.
    """
    canonical = SPDX_LICENSES.get((spdx_id or "").strip())
    if canonical is not None:
        return ResolvedLicense(name=canonical[0], url=canonical[1])
    return ResolvedLicense(name=(name or "").strip() or None, url=(url or "").strip() or None)
