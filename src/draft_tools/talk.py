"""Talk the post: a spoken first draft, slotted into the outline's sections as your words.

Speaking a draft costs a fraction of typing one. The transcript is split into numbered
sentences and the model only decides which section each sentence belongs to; the text
itself is rebuilt from your sentences here, so the model can't add words even if it
wants to (a small local model given "rewrite faithfully" copied outline text and
padded the draft). Filler words are removed by rule, and every sentence the model
doesn't place lands under "Spoken, not yet placed" -- nothing is dropped.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from .outline import Note, Section, parse_note

AUDIO_EXTENSIONS = {".m4a", ".wav", ".mp3", ".aac", ".caf"}
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
UNPLACED_HEADING = "Spoken, not yet placed"

SYSTEM_PROMPT = """You sort the sentences of a spoken first draft into the sections of a blog post outline.

You are given the section headings, each with a short hint of what the outline plans for it,
and the transcript as numbered sentences. For every sentence number, choose the one heading
it belongs under, or "none" if it fits no section (asides, off-topic remarks).
Keep sentences that continue the same thought in the same section.
Use the headings exactly as given. Do not rewrite or quote any text.

Return JSON: {"assignments": [{"sentence": 1, "heading": "..."}, ...]}"""

_FILLER_WORD = r"(?:um+|uh+|erm+|er|ah+)"
_FILLERS = [
    (re.compile(rf",\s*{_FILLER_WORD}\s*,\s*", re.IGNORECASE), " "),
    (re.compile(rf"\b{_FILLER_WORD}\b[,.]?\s*", re.IGNORECASE), ""),
    (re.compile(r",\s*(?:like|you know|I mean|sort of|kind of),\s*", re.IGNORECASE), ", "),
    (re.compile(r"^(?:okay|ok|so|well|right|alright)[,.]?\s+(?:so[,.]?\s+)?", re.IGNORECASE), ""),
    (re.compile(r"\s{2,}"), " "),
]


class Assignment(BaseModel):
    sentence: int
    heading: str


class Assignments(BaseModel):
    assignments: list[Assignment]


@dataclass
class TalkReport:
    placed: dict[str, int] = field(default_factory=dict)  # heading -> sentences
    unplaced: int = 0
    sentences: int = 0


def read_transcript(path: Path) -> str:
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        return path.read_text(encoding="utf-8").strip()
    try:
        import mlx_whisper  # pyright: ignore[reportMissingImports]  # optional 'voice' extra, Apple silicon only
    except ImportError as e:
        raise RuntimeError(
            "Audio needs mlx-whisper: uv tool install --reinstall '~/projects/local-first/draft-tools[voice]'"
        ) from e
    result = mlx_whisper.transcribe(str(path), path_or_hf_repo=WHISPER_MODEL)
    return (result.get("text") or "").strip()


def split_sentences(transcript: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", transcript).strip())
    return [p for p in parts if p]


def clean(sentence: str) -> str:
    """Remove spoken filler only; every other word is kept as said."""
    for pattern, repl in _FILLERS:
        sentence = pattern.sub(repl, sentence)
    sentence = sentence.strip(" ,")
    return sentence[:1].upper() + sentence[1:] if sentence else ""


def _hint(section: Section) -> str:
    text = re.sub(
        r"```.*?```",
        "",
        re.sub(r"<!--\s*(?:~\d+ words|test:[^>]*|TODO[^>]*)-->", "", section.text, flags=re.DOTALL),
        flags=re.DOTALL,
    )
    text = re.sub(r"<!-- outline:|-->|\|[^\n]*\||[#*_`>]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:200]


def build_prompt(note: Note, sentences: list[str]) -> str:
    headings = "\n".join(f"- {s.heading}: {_hint(s)}" for s in note.body_sections)
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
    return f"Post title: {note.title}\n\nSections:\n{headings}\n\nSentences:\n{numbered}"


def _match(heading: str, sections: list[Section]) -> Section | None:
    norm = heading.strip().lower().lstrip("#").strip()
    return next((s for s in sections if s.heading.lower() == norm), None)


def assign(note: Note, sentences: list[str], result: Assignments) -> dict[int, Section | None]:
    """sentence index (1-based) -> section, None meaning unplaced. Every sentence gets an entry."""
    placement: dict[int, Section | None] = dict.fromkeys(range(1, len(sentences) + 1))
    for a in result.assignments:
        if a.sentence in placement:
            placement[a.sentence] = _match(a.heading, note.body_sections)
    return placement


def merge(note: Note, sentences: list[str], placement: dict[int, Section | None], source_name: str) -> TalkReport:
    marker = f"<!-- spoken draft (rough, from {source_name}): edit into prose, then delete this line -->\n"
    report = TalkReport(sentences=len(sentences))
    by_section: dict[int, list[str]] = {}
    unplaced: list[str] = []
    for i, section in placement.items():
        text = clean(sentences[i - 1])
        if not text:
            continue
        if section is None:
            unplaced.append(text)
        else:
            by_section.setdefault(id(section), []).append(text)
    for section in note.body_sections:
        texts = by_section.get(id(section))
        if not texts:
            continue
        at = next((i for i, ln in enumerate(section.lines) if not ln.startswith("<!-- ~")), len(section.lines))
        section.lines[at:at] = [marker, " ".join(texts) + "\n", "\n"]
        report.placed[section.heading] = len(texts)
    if unplaced:
        if note.sections[-1].lines and not note.sections[-1].lines[-1].endswith("\n"):
            note.sections[-1].lines[-1] += "\n"
        note.sections.append(Section(f"## {UNPLACED_HEADING}\n", [marker, " ".join(unplaced) + "\n"]))
        report.unplaced = len(unplaced)
    return report


def talk(note_text: str, transcript: str, provider, source_name: str) -> tuple[str, TalkReport]:
    note = parse_note(note_text)
    if not note.body_sections:
        raise ValueError("the note has no ## sections to place the transcript into")
    sentences = split_sentences(transcript)
    if not sentences:
        raise ValueError("the transcript is empty")
    result = provider.complete(SYSTEM_PROMPT, build_prompt(note, sentences), response_model=Assignments)
    report = merge(note, sentences, assign(note, sentences, result), source_name)
    return note.render(), report
