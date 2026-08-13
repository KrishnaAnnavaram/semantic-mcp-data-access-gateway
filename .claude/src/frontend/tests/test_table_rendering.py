"""Markdown tables must reach Streamlit's renderer, not the escaped bubble.

The chat bubble is hand-built HTML, so its contents are escaped — correct for
prose (an answer must never inject markup) and wrong for tables, which arrived
as markdown and were shown to the user as literal rows of `|` characters.

`split_markdown_tables` is what separates the two. These tests pin the boundary
detection, because the failure mode is silent: a mis-split table renders as
either raw pipes or, worse, escaped prose that looks almost right.
"""

from __future__ import annotations

from app import split_markdown_tables

TABLE = """| Tenor | Yield (%) |
|---|---|
| 1M | 3.79 |
| 2Y | 4.22 |
| 10Y | 4.70 |"""


def kinds(text):
    return [kind for kind, _ in split_markdown_tables(text)]


def test_a_bare_table_is_detected_as_a_table():
    assert kinds(TABLE) == ["table"]


def test_prose_alone_is_never_treated_as_a_table():
    assert kinds("The 2s10s slope is +48.0 bp as of 2026-08-11.") == ["prose"]


def test_prose_then_table_then_prose_splits_into_three():
    text = f"Both curves as of 2026-08-11.\n\n{TABLE}\n\nSource: Treasury."
    assert kinds(text) == ["prose", "table", "prose"]


def test_the_table_segment_keeps_every_row():
    text = f"Intro.\n\n{TABLE}\n\nOutro."
    table = next(body for kind, body in split_markdown_tables(text) if kind == "table")
    assert "| 1M | 3.79 |" in table
    assert "| 10Y | 4.70 |" in table


def test_two_tables_are_kept_separate():
    text = f"Nominal:\n\n{TABLE}\n\nReal:\n\n{TABLE}"
    assert kinds(text) == ["prose", "table", "prose", "table"]


def test_a_pipe_in_prose_is_not_a_table():
    """No separator row, so it is a sentence that happens to contain a pipe."""
    assert kinds("Use the | character to separate fields.") == ["prose"]


def test_a_row_without_a_separator_row_is_not_a_table():
    """The separator is what distinguishes a table from pipe-wrapped prose."""
    assert kinds("| this looks like a row |\n| and so does this |") == ["prose"]


def test_an_alignment_separator_is_still_recognised():
    aligned = "| Tenor | Yield |\n|:---|---:|\n| 2Y | 4.22 |"
    assert kinds(aligned) == ["table"]


def test_empty_content_produces_no_segments():
    assert split_markdown_tables("") == []


def test_whitespace_only_content_produces_no_segments():
    assert split_markdown_tables("\n\n   \n") == []


def test_segments_reassemble_into_the_original_content():
    """Nothing may be dropped on the way to the renderer."""
    text = f"Intro line.\n\n{TABLE}\n\nClosing line."
    rejoined = "\n".join(body for _, body in split_markdown_tables(text))
    for line in text.split("\n"):
        if line.strip():
            assert line in rejoined
