"""Extraction of key/value data from the original Clariot report.

The reports are laid out as a grid, not as prose, and plain text extraction
mangles them: every label of a row lands on one line and every value on the
next, with no separator that says which value belongs to which label. So the
primary strategy is positional — words are grouped into rows and cells by their
coordinates on the page, and a value is looked for either to the right of its
label or directly underneath it.

A line-based pass runs afterwards for anything the positional pass missed, which
covers reports laid out as simple "LABEL: value" text.

Everything below ``parse_pdf`` works on plain data, so the interesting behaviour
is testable without a PDF.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .models import AlertReport
from .textutils import normalize

logger = logging.getLogger(__name__)

# --- positional parsing -----------------------------------------------------

# Words closer than this horizontally belong to the same word (the generator
# splits glyphs), further apart than CELL_GAP they belong to different cells.
# Measured on real reports: intra-cell gaps are 0-5pt, inter-cell gaps 115pt+.
JOIN_GAP = 1.0
CELL_GAP = 30.0
# Vertical tolerance when grouping words into a row.
ROW_TOLERANCE = 6.0
# How far below a label its value may sit.
BELOW_DISTANCE = 40.0
# Maximum vertical step for a wrapped paragraph to count as a continuation.
CONTINUATION_GAP = 30.0
# How far a column value's left edge may drift from its header's.
COLUMN_TOLERANCE = 20.0

SOFT_HYPHEN = "­"


@dataclass(frozen=True)
class Cell:
    """A run of text on the page, with the coordinates it was found at."""
    text: str
    x0: float
    x1: float
    top: float


def _clean(text: str) -> str:
    # The generator emits soft hyphens inside dates and serial numbers, which
    # render as nothing in an email body.
    return re.sub(r"\s+", " ", text.replace(SOFT_HYPHEN, "-")).strip()


def build_rows(words: Sequence[Mapping]) -> list[list[Cell]]:
    """Group positioned words into rows of cells.

    ``words`` are pdfplumber word dicts (``text``, ``x0``, ``x1``, ``top``).
    """
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[Mapping]] = []
    for word in ordered:
        if rows and abs(word["top"] - rows[-1][0]["top"]) <= ROW_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])

    result: list[list[Cell]] = []
    for row in rows:
        row = sorted(row, key=lambda w: w["x0"])
        cells: list[Cell] = []
        text, x0, x1, top = row[0]["text"], row[0]["x0"], row[0]["x1"], row[0]["top"]

        for word in row[1:]:
            gap = word["x0"] - x1
            if gap >= CELL_GAP:
                cells.append(Cell(_clean(text), x0, x1, top))
                text, x0 = word["text"], word["x0"]
            elif gap < JOIN_GAP:
                text += word["text"]
            else:
                text += " " + word["text"]
            x1 = word["x1"]

        cells.append(Cell(_clean(text), x0, x1, top))
        result.append(cells)
    return result


def _label_key(text: str) -> str:
    """Normalized form of a cell, ignoring a trailing colon."""
    return normalize(text).rstrip(":").strip()


def read_pages(pdf_path: Path) -> list[tuple[list[dict], str]]:
    """Return ``(positioned words, plain text)`` for every page.

    PyMuPDF rather than pdfplumber, for a measured reason: these reports embed a
    font subset with an incomplete Unicode map, and pdfplumber emits NUL for
    every unmapped glyph. On a real report "Notification" came out as
    "Noti\\x00cation" and the event year 2026 as "202\\x00", which would have
    silently corrupted the event timestamps the grouping depends on. PyMuPDF
    resolves those glyphs correctly.
    """
    import pymupdf  # imported lazily to keep test collection fast

    pages: list[tuple[list[dict], str]] = []
    with pymupdf.open(str(pdf_path)) as document:
        for page in document:
            words = [
                {"text": word[4], "x0": word[0], "x1": word[2], "top": word[1]}
                for word in page.get_text("words")
            ]
            pages.append((words, page.get_text()))
    return pages


def parse_layout(
    rows: Sequence[Sequence[Cell]],
    labels: Mapping[str, Sequence[str]],
    noise: Sequence[str] = (),
) -> dict[str, str]:
    """Resolve labels to values using cell positions."""
    known = {normalize(alias) for aliases in labels.values() for alias in aliases}
    found: dict[str, str] = {}

    def is_label(cell: Cell) -> bool:
        return _label_key(cell.text) in known

    for row_index, row in enumerate(rows):
        for cell_index, cell in enumerate(row):
            key = _label_key(cell.text)
            canonical = next(
                (
                    name
                    for name, aliases in labels.items()
                    if name not in found and key in {normalize(a) for a in aliases}
                ),
                None,
            )
            if canonical is None:
                continue

            # Value to the right, unless that cell is itself a label: a row of
            # four column headers must not consume its neighbours as values.
            if cell_index + 1 < len(row) and not is_label(row[cell_index + 1]):
                value_cell, start_row = row[cell_index + 1], row_index
                # Only a label-left/value-right field wraps onto further lines.
                text = _join_continuation(rows, start_row, value_cell, is_label)
            else:
                value_cell, start_row = _cell_below(rows, row_index, cell, is_label)
                if value_cell is None:
                    continue
                # A column value is a single line. Absorbing the line below would
                # swallow the next column's value: real reports render the
                # SECTION value underneath the PLANT column.
                text = value_cell.text

            found[canonical] = _strip_noise(text, noise)

    return found


def _same_column(cell: Cell, label: Cell) -> bool:
    """True when the cell starts under the label, i.e. shares its column.

    Left-edge alignment, not bounding-box overlap. Measured on real reports:
    every column value starts at exactly its header's x0, while a wide neighbour
    value can overlap a header's box by a point or two and would otherwise be
    stolen. It also keeps an empty column empty — SENSOR ID arrives with no
    value, and borrowing the neighbour's would be worse than reporting nothing.
    """
    return abs(cell.x0 - label.x0) <= COLUMN_TOLERANCE


def _cell_below(
    rows: Sequence[Sequence[Cell]], row_index: int, label: Cell, is_label
) -> tuple[Cell | None, int]:
    """Find the value cell under a column header."""
    for offset, row in enumerate(rows[row_index + 1 :], start=row_index + 1):
        if not row or row[0].top - label.top > BELOW_DISTANCE:
            return None, offset
        for cell in row:
            if _same_column(cell, label) and not is_label(cell):
                return cell, offset
    return None, row_index


def _join_continuation(
    rows: Sequence[Sequence[Cell]], row_index: int, value: Cell, is_label
) -> str:
    """Append wrapped lines of a paragraph value.

    A recommended-action paragraph spans several rows. Continuation stops at the
    next row that carries a label, or when the vertical step gets too large.
    """
    parts = [value.text]
    previous_top = value.top

    for row in rows[row_index + 1 :]:
        if not row or any(is_label(cell) for cell in row):
            break
        if row[0].top - previous_top > CONTINUATION_GAP:
            break
        continuation = [cell for cell in row if _same_column(cell, value)]
        if len(continuation) != len(row) or not continuation:
            break
        parts.append(" ".join(cell.text for cell in continuation))
        previous_top = row[0].top

    return " ".join(parts)


def _strip_noise(value: str, noise: Sequence[str]) -> str:
    """Remove configured junk fragments, leaving everything else untouched.

    Values must come out byte-identical to the report: an asset tag can legally
    end in a hyphen or a period, so separators are only trimmed when a noise
    fragment was actually removed and left a dangling one behind.
    """
    cleaned = value
    for fragment in noise:
        cleaned = re.sub(re.escape(fragment), "", cleaned, flags=re.IGNORECASE)

    if cleaned == value:
        return value.strip()
    return re.sub(r"\s+", " ", cleaned).strip(" -:;,")


# --- line-based fallback ----------------------------------------------------

_SEPARATORS = ":;=–—|\t"
_WIDE_GAP = re.compile(r"\s{2,}")
_LEADING_NOISE = re.compile(r"^[\s\-•●\*\d\.\)]+")


def split_label_value(line: str) -> tuple[str, str] | None:
    """Split ``"MACHINE NAME: Bba retor"`` into ``("MACHINE NAME", "Bba retor")``.

    Splits on the first separator character, then falls back to a wide
    whitespace gap. Returns ``None`` when the line holds no separator at all.
    Only the label side is normalized later, so the value keeps its original
    casing and accents.
    """
    for index, char in enumerate(line):
        if char in _SEPARATORS:
            return line[:index].strip(), line[index + 1 :].strip()

    match = _WIDE_GAP.search(line.strip())
    if match:
        stripped = line.strip()
        return stripped[: match.start()].strip(), stripped[match.end() :].strip()
    return None


def _matches_label(candidate: str, label: str) -> bool:
    cleaned = _label_key(_LEADING_NOISE.sub("", candidate))
    target = normalize(label).rstrip(":").strip()
    if not cleaned or not target:
        return False
    return cleaned == target or cleaned.endswith(" " + target)


def parse_report(
    lines: Iterable[str], labels: Mapping[str, Sequence[str]]
) -> AlertReport:
    """Map configured labels onto the first matching value found in ``lines``."""
    pending_field: str | None = None
    found: dict[str, str] = {}
    materialized = [line for line in lines if line and line.strip()]

    for raw_line in materialized:
        line = raw_line.strip()

        # A label found on the previous line with no value takes this line.
        if pending_field and split_label_value(line) is None:
            found[pending_field] = line
            pending_field = None
            continue
        pending_field = None

        parts = split_label_value(line)
        if parts is None:
            continue
        candidate, value = parts

        for canonical, aliases in labels.items():
            if canonical in found:
                continue
            if not any(_matches_label(candidate, alias) for alias in aliases):
                continue
            if value:
                found[canonical] = value
            else:
                # Label alone on its line; the value is probably the next one.
                pending_field = canonical
            break

    return AlertReport(fields=found)


# --- entry point ------------------------------------------------------------


def parse_pdf(
    pdf_path: Path, labels: Mapping[str, Sequence[str]], noise: Sequence[str] = ()
) -> AlertReport:
    """Extract the report fields from a PDF file on disk."""
    found: dict[str, str] = {}
    lines: list[str] = []

    for words, text in read_pages(pdf_path):
        rows = build_rows(words)
        for name, value in parse_layout(rows, labels, noise).items():
            found.setdefault(name, value)
        lines.extend(text.splitlines())

    # Second pass for reports laid out as plain "LABEL: value" lines.
    for name, value in parse_report(lines, labels).fields.items():
        found.setdefault(name, _strip_noise(value, noise))

    report = AlertReport(fields=found)
    if report.is_empty:
        logger.warning(
            "No configured label matched in %s; the draft will be incomplete. "
            "Add the real labels to config/pdf_labels.yaml.",
            pdf_path.name,
        )
    return report
