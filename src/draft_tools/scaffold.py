"""Turn an outline note into a drafting skeleton, without writing any of the post.

What's already prose, code or a table stays as it is. Bullet lists become HTML
comments (prompts to write over, then delete). Each section gets a word budget,
the title gets a direct-answer slot, fill-in markers are collected at the top, and
every code block without a test annotation gets `test:skip` so blog-validate --
which starts running a post's code once it leaves `outline` -- doesn't execute
illustrative snippets.
"""

import re
from dataclasses import dataclass, field

from .outline import (
    FENCE,
    Note,
    Section,
    frontmatter_value,
    parse_note,
    set_frontmatter_value,
)

DIRECT_ANSWER = "<!-- Direct answer (~50 words): answer the title plainly, first, for readers and AI summaries. -->\n"
FILL_IN = re.compile(r"\[fill[^\]]*\]|\*?\(fill in[^)]*\)\*?", re.IGNORECASE)
BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
ANNOTATION = re.compile(r"^\s*<!--\s*test:")
SKIP_NOTE = "<!-- TODO: test:skip was added by draft-scaffold; replace it with a real annotation once this code is final -->\n"


class ScaffoldError(Exception):
    """The note can't be scaffolded as asked (wrong status, already scaffolded)."""


@dataclass
class ScaffoldReport:
    sections: int = 0
    budget: int = 0
    outline_blocks: int = 0
    code_skipped: int = 0
    fill_ins: list[str] = field(default_factory=list)


def _comment_block(lines: list[str]) -> list[str]:
    return ["<!-- outline:\n", *(ln.replace("-->", "- ->") for ln in lines), "-->\n"]


def scaffold_lines(lines: list[str], report: ScaffoldReport, heading: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if FENCE.match(line):
            prev = next((ln for ln in reversed(out) if ln.strip()), "")
            if not ANNOTATION.match(prev):
                out += [SKIP_NOTE, "<!-- test:skip -->\n"]
                report.code_skipped += 1
            out.append(line)
            i += 1
            while i < len(lines):
                out.append(lines[i])
                i += 1
                if FENCE.match(lines[i - 1]):
                    break
            continue
        if BULLET.match(line):
            block = []
            while i < len(lines) and (BULLET.match(lines[i]) or (lines[i].startswith((" ", "\t")) and lines[i].strip())):
                block.append(lines[i])
                i += 1
            out += _comment_block(block)
            report.outline_blocks += 1
            continue
        for m in FILL_IN.finditer(line):
            report.fill_ins.append(f"{heading or 'intro'}: {m.group(0).strip('*()[] ')}")
        out.append(line)
        i += 1
    return out


def scaffold(text: str, target_words: int = 1200, force: bool = False) -> tuple[str, ScaffoldReport]:
    note: Note = parse_note(text)
    status = frontmatter_value(note.frontmatter, "status")
    if status != "outline" and not force:
        raise ScaffoldError(f"status is {status!r}, not 'outline' (pass force to scaffold anyway)")
    if DIRECT_ANSWER.strip() in text:
        raise ScaffoldError("already scaffolded")

    report = ScaffoldReport(sections=len(note.body_sections))
    report.budget = max(50, round(target_words / max(1, report.sections) / 25) * 25)

    for section in note.body_sections:
        section.lines = [f"<!-- ~{report.budget} words -->\n", *scaffold_lines(section.lines, report, section.heading)]

    preamble = note.sections[0]
    title_at = next((i for i, ln in enumerate(preamble.lines) if ln.startswith("# ")), None)
    header = [DIRECT_ANSWER]
    todo = [f"- {f}\n" for f in report.fill_ins]
    if report.code_skipped:
        todo.append(f"- {report.code_skipped} code block(s) marked test:skip: give each a real test annotation\n")
    if todo:
        header += ["<!-- TODO before publishing:\n", *todo, "-->\n"]
    insert_at = 0 if title_at is None else title_at + 1
    preamble.lines[insert_at:insert_at] = ["\n", *header] if title_at is not None else [*header, "\n"]

    if note.frontmatter is not None:
        note.frontmatter = set_frontmatter_value(note.frontmatter, "status", "draft")
    return note.render(), report


def section_of(note: Note, heading: str) -> Section | None:
    return next((s for s in note.body_sections if s.heading == heading), None)
