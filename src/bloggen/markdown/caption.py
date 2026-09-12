"""Image captions as bold/italic text runs.

A caption is stored in Markdown as the image's alt text, where ``**`` and
``*`` are kept literally so the emphasis reaches the published figure
(see ``rich_text_export._run_to_md``). Editors that let authors type the
caption directly need both directions: markers → runs to display it, and
runs → markers to store it. Only bold and italic exist in a caption.

Emphasis follows Pandoc's flanking rule: an opening marker must be followed
by a non-space and a closing one preceded by a non-space, so ``5 * 3 * 2``
stays literal.
"""

from __future__ import annotations

import re

from bloggen.markdown.rich_text_model import InlineRun

_EMPHASIS_RE = re.compile(
    r"\*\*\*(?=[^\s*])(?P<both>.+?)(?<=[^\s*])\*\*\*"
    r"|\*\*(?=[^\s*])(?P<bold>.+?)(?<=[^\s*])\*\*"
    r"|\*(?=[^\s*])(?P<italic>[^*]+?)(?<=[^\s*])\*"
)


def caption_runs(caption: str | None) -> list[InlineRun]:
    """Split a stored caption into merged text runs (bold/italic only)."""

    runs: list[InlineRun] = []
    text = caption or ""
    position = 0
    for match in _EMPHASIS_RE.finditer(text):
        if match.start() > position:
            _append(runs, InlineRun(text=text[position : match.start()]))
        if match.group("both") is not None:
            _append(runs, InlineRun(text=match.group("both"), bold=True, italic=True))
        elif match.group("bold") is not None:
            _append(runs, InlineRun(text=match.group("bold"), bold=True))
        else:
            _append(runs, InlineRun(text=match.group("italic"), italic=True))
        position = match.end()
    if position < len(text):
        _append(runs, InlineRun(text=text[position:]))
    return runs


def caption_markdown(runs: list[InlineRun]) -> str:
    """Serialize caption runs back to ``**``/``*`` markers.

    Only ``text``, ``bold`` and ``italic`` are read; spaces at the edge of an
    emphasised run are moved outside its markers so they stay valid.
    """

    parts: list[str] = []
    for run in normalize_caption_runs(runs):
        marker = ("***" if run.italic else "**") if run.bold else ("*" if run.italic else "")
        core = run.text
        if not marker or not core.strip():
            parts.append(core)
            continue
        stripped = core.strip()
        leading = core[: len(core) - len(core.lstrip())]
        trailing = core[len(core.rstrip()) :]
        parts.append(f"{leading}{marker}{stripped}{marker}{trailing}")
    return "".join(parts)


def normalize_caption_runs(runs: list[InlineRun]) -> list[InlineRun]:
    """Keep only what a caption can express, merging equal neighbours."""

    result: list[InlineRun] = []
    for run in runs:
        if run.image_src is not None or run.footnote_ref is not None or not run.text:
            continue
        _append(result, InlineRun(text=run.text, bold=run.bold, italic=run.italic))
    return result


def flatten_caption_text(text: str) -> str:
    """A caption is one line: collapse line breaks and runs of blanks."""

    return re.sub(r"[\r\n  \t]+", " ", text)


def _append(runs: list[InlineRun], run: InlineRun) -> None:
    if not run.text:
        return
    if runs and (runs[-1].bold, runs[-1].italic) == (run.bold, run.italic):
        runs[-1] = InlineRun(
            text=runs[-1].text + run.text, bold=run.bold, italic=run.italic
        )
    else:
        runs.append(run)
