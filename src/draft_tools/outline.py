"""Read a vault post note as title + H2 sections, code-fence aware.

parse_note(text).render() == text for any note, so tools can edit one section and
leave the rest byte-for-byte alone.
"""

import re
from dataclasses import dataclass, field

from local_first_common.obsidian import split_frontmatter

FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Section:
    heading_line: str  # "## Heading\n", or "" for text before the first H2
    lines: list[str] = field(default_factory=list)

    @property
    def heading(self) -> str:
        return self.heading_line[3:].strip()

    @property
    def text(self) -> str:
        return "".join(self.lines)


@dataclass
class Note:
    frontmatter: str | None  # raw YAML block, or None if the note has none
    sections: list[Section]  # sections[0] is the preamble (title and anything before the first H2)
    head: str = ""  # the original text before the body: delimiters + YAML, verbatim
    original_frontmatter: str | None = None

    @property
    def title(self) -> str:
        for line in self.sections[0].lines:
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    @property
    def body_sections(self) -> list[Section]:
        return self.sections[1:]

    def render(self) -> str:
        body = "".join(s.heading_line + s.text for s in self.sections)
        head = self.head
        if self.frontmatter != self.original_frontmatter and self.original_frontmatter is not None:
            head = head.replace(self.original_frontmatter, self.frontmatter or "", 1)
        return head + body


def parse_note(text: str) -> Note:
    parts = split_frontmatter(text)
    raw, body = parts if parts else (None, text)
    sections = [Section("")]
    in_fence = False
    for line in body.splitlines(keepends=True):
        if FENCE.match(line):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            sections.append(Section(line))
            continue
        sections[-1].lines.append(line)
    head = text[: len(text) - len(body)] if parts else ""
    return Note(raw, sections, head, raw)


def frontmatter_value(raw: str | None, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", raw or "", re.MULTILINE)
    return m.group(1).strip("'\"") if m else None


def set_frontmatter_value(raw: str, key: str, value: str) -> str:
    line = f"{key}: {value}\n"
    new, n = re.subn(rf"^{re.escape(key)}:.*\n", line, raw, count=1, flags=re.MULTILINE)
    return new if n else raw + line
