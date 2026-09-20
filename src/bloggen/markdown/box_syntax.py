"""Reserved Markdown syntax of the Mérope *encadré* (``BOX``) block.

A box is a Pandoc fenced div carrying a Mérope-only class::

    :::: {.merope-encadre}
    ::: {.merope-encadre-titre}
    À retenir
    :::

    Premier paragraphe.

    Deuxième paragraphe.
    ::::

The optional title is its own nested div rather than a Markdown heading, so
it never takes part in :func:`bloggen.tei.postprocess.extract_heading_levels`
(which only looks at ATX/Setext headings) and cannot shift the levels of the
document's real headings. The Pandoc Lua filter shipped in
``resources/pandoc/merope_encadre.lua`` turns this syntax into the native
TEI Commons Publishing ``floatingText``; the class names below must stay in
sync with it.
"""

from __future__ import annotations

import re

BOX_CLASS = "merope-encadre"
BOX_TITLE_CLASS = "merope-encadre-titre"

BOX_OPEN = f":::: {{.{BOX_CLASS}}}"
BOX_CLOSE = "::::"
BOX_TITLE_OPEN = f"::: {{.{BOX_TITLE_CLASS}}}"
BOX_TITLE_CLOSE = ":::"

# Any fenced-div fence (opening or closing); such a line is never plain
# paragraph text for the importer.
FENCED_DIV_LINE_RE = re.compile(r"^ {0,3}:{3,}")
