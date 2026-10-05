import pytest

from draft_tools.outline import parse_note
from draft_tools.scaffold import DIRECT_ANSWER, SKIP_NOTE, ScaffoldError, scaffold

OUTLINE = """---
status: outline
tags: [x]
---

# Can a Model Do It?

## Hook
This paragraph is already prose.

## The Setup
- **Task:** one
- **Models:** two
  continued detail

| a | b |
|---|---|
| 1 | 2 |

## The Code
```python
print("illustrative")
```

<!-- test:assert -->
```python
assert True
```

## What I Found
*(Fill in from actual observations)*
**The verdict:** [fill from observations]
"""


def test_round_trip_is_exact():
    for text in (
        OUTLINE,
        "no frontmatter\n## A\nb",
        "---\na: 1\n---",
        "---\na: 1\n---\n## X\n```\n## not a heading\n```\n",
    ):
        assert parse_note(text).render() == text


def test_scaffold_structure():
    out, report = scaffold(OUTLINE, target_words=800)
    assert "status: draft" in out and "status: outline" not in out
    assert out.index(DIRECT_ANSWER) > out.index("# Can a Model Do It?")
    assert report.sections == 4 and report.budget == 200
    assert out.count("<!-- ~200 words -->") == 4
    assert "This paragraph is already prose." in out
    assert "<!-- outline:\n- **Task:** one\n- **Models:** two\n  continued detail\n-->" in out
    assert "| 1 | 2 |" in out


def test_only_unannotated_code_gets_skip():
    out, report = scaffold(OUTLINE)
    assert report.code_skipped == 1
    assert f"{SKIP_NOTE}<!-- test:skip -->\n```python\nprint" in out
    assert "<!-- test:assert -->\n```python\nassert True" in out


def test_fill_ins_are_collected_at_the_top():
    out, report = scaffold(OUTLINE)
    assert report.fill_ins == ["What I Found: Fill in from actual observations", "What I Found: fill from observations"]
    assert out.index("TODO before publishing") < out.index("## Hook")


def test_refuses_non_outline_and_rescaffold():
    with pytest.raises(ScaffoldError):
        scaffold(OUTLINE.replace("status: outline", "status: draft"))
    once, _ = scaffold(OUTLINE)
    with pytest.raises(ScaffoldError):
        scaffold(once, force=True)


def test_comment_terminator_inside_bullets_is_neutralized():
    out, _ = scaffold("---\nstatus: outline\n---\n# T\n## A\n- arrow --> here\n")
    assert "- arrow - -> here" in out
