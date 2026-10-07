"""Filesystem-path constants shared across otherwise unrelated parts of the
codebase — kept here instead of in whichever of those parts defined it
first, so neither has to import from the other just to stay in sync.
"""

from __future__ import annotations

# Entries MEROPE never produces itself, but that can legitimately sit at the
# root of an output directory also used as a Git working tree (e.g. a
# GitHub Pages mirror): see bloggen.build.site_builder, which carries them
# over intact across a full output-directory rebuild, and
# bloggen.publish.ftp_publisher, which never uploads them.
EXTERNAL_OUTPUT_ENTRIES: tuple[str, ...] = (".git", ".gitignore", ".nojekyll")
