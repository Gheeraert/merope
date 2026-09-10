"""Identifiants et styles partages par l'adaptateur documentaire Qt."""

from PySide6.QtGui import QTextFormat


_MEROPE_PROPERTY_BASE = int(QTextFormat.Property.UserProperty)

# Proprietes de bloc.
BLOCK_KIND_PROPERTY = _MEROPE_PROPERTY_BASE + 1
HEADING_LEVEL_PROPERTY = _MEROPE_PROPERTY_BASE + 2
ALIGNMENT_PROPERTY = _MEROPE_PROPERTY_BASE + 3
LIST_KIND_PROPERTY = _MEROPE_PROPERTY_BASE + 4

# Proprietes de caracteres. Elles portent la semantique Merope independamment
# du rendu visuel choisi pour le QTextDocument.
BOLD_PROPERTY = _MEROPE_PROPERTY_BASE + 20
ITALIC_PROPERTY = _MEROPE_PROPERTY_BASE + 21
STRIKETHROUGH_PROPERTY = _MEROPE_PROPERTY_BASE + 22
SUPERSCRIPT_PROPERTY = _MEROPE_PROPERTY_BASE + 23

HEADING_POINT_SIZES = {1: 24.0, 2: 20.0, 3: 17.0, 4: 15.0}
BODY_POINT_SIZE = 11.0
BLOCKQUOTE_LEFT_MARGIN = 24.0

