"""GUI-independent semantic operations for rich-text footnotes."""

from __future__ import annotations

from dataclasses import dataclass

from bloggen.markdown.rich_text_model import FOOTNOTE_DEFINITION, Block, InlineRun


FootnoteDefinitions = dict[str, list[InlineRun]]


def footnote_reference_order(blocks: list[Block]) -> list[str]:
    """Return every semantic reference ID in document reading order."""

    references: list[str] = []

    def visit(block: Block) -> None:
        references.extend(
            run.footnote_ref
            for run in block.runs
            if run.footnote_ref is not None
        )
        for child in block.children:
            visit(child)

    for block in blocks:
        visit(block)
    return references


def footnote_reference_counts(blocks: list[Block]) -> dict[str, int]:
    """Count semantic references without inspecting their visible marker text."""

    counts: dict[str, int] = {}
    for note_id in footnote_reference_order(blocks):
        counts[note_id] = counts.get(note_id, 0) + 1
    return counts


def separate_footnote_definitions(
    blocks: list[Block],
) -> tuple[list[Block], FootnoteDefinitions]:
    """Separate body blocks from canonical footnote-definition blocks."""

    body: list[Block] = []
    definitions: FootnoteDefinitions = {}
    for block in blocks:
        if block.kind != FOOTNOTE_DEFINITION:
            body.append(block)
            continue
        note_id = block.footnote_id
        if not isinstance(note_id, str) or not note_id:
            raise ValueError("Une définition de note doit avoir un identifiant")
        if note_id in definitions:
            raise ValueError(f"Définition de note dupliquée : {note_id}")
        definitions[note_id] = block.runs
    return body, definitions


def footnote_definition_blocks(
    definitions: FootnoteDefinitions,
) -> list[Block]:
    """Rebuild canonical definition blocks in stored insertion order."""

    return [
        Block(kind=FOOTNOTE_DEFINITION, footnote_id=note_id, runs=runs)
        for note_id, runs in definitions.items()
    ]


@dataclass(slots=True)
class FootnoteRenumbering:
    """A renumbering plan for definitions and GUI-rendered references."""

    mapping: dict[str, str]
    definitions: FootnoteDefinitions

    @property
    def changed(self) -> bool:
        return any(old_id != new_id for old_id, new_id in self.mapping.items())


def next_footnote_id(definitions: FootnoteDefinitions) -> str:
    """Return the first free positive integer identifier as text."""
    next_id = 1
    while str(next_id) in definitions:
        next_id += 1
    return str(next_id)


def register_footnote(
    definitions: FootnoteDefinitions,
    note_content: str | list[InlineRun],
) -> str:
    """Allocate the next identifier and add one definition in place."""
    note_id = next_footnote_id(definitions)
    runs = [InlineRun(text=note_content)] if isinstance(note_content, str) else note_content
    definitions[note_id] = runs or [InlineRun(text="")]
    return note_id


def remove_footnote(definitions: FootnoteDefinitions, note_id: str) -> bool:
    """Remove a definition in place and report whether it existed."""
    if note_id not in definitions:
        return False
    del definitions[note_id]
    return True


def ordered_footnote_ids(
    definitions: FootnoteDefinitions,
    reference_order: list[str] | tuple[str, ...],
) -> list[str]:
    """Return unique referenced ids followed by numeric orphan ids.

    References that have no definition are retained, matching the editor's
    historical behaviour: its visible marker can still be renumbered even
    when no corresponding panel row exists.
    """
    seen: list[str] = []
    for note_id in reference_order:
        if note_id not in seen:
            seen.append(note_id)
    orphans = sorted((note_id for note_id in definitions if note_id not in seen), key=int)
    return seen + orphans


def plan_footnote_renumbering(
    definitions: FootnoteDefinitions,
    reference_order: list[str] | tuple[str, ...],
) -> FootnoteRenumbering:
    """Build a numbering map and renamed definitions without touching a GUI."""
    ordered_old_ids = ordered_footnote_ids(definitions, reference_order)
    mapping = {old_id: str(index + 1) for index, old_id in enumerate(ordered_old_ids)}
    renamed = {
        mapping[old_id]: runs
        for old_id, runs in definitions.items()
        if old_id in mapping
    }
    return FootnoteRenumbering(mapping=mapping, definitions=renamed)
