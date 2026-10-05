"""draft: move vault post outlines toward drafts."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from local_first_common.cli import (
    dry_run_option,
    json_option,
    model_option,
    provider_option,
    resolve_provider,
)
from local_first_common.obsidian import parse_frontmatter
from local_first_common.tracking import register_tool, timed_run

from .scaffold import ScaffoldError, scaffold
from .talk import UNPLACED_HEADING, read_transcript, talk

TOOL = "draft-tools"
_TOOL = register_tool(TOOL)
BACKUP_DIR = Path.home() / ".local" / "share" / "draft-tools" / "backups"
VAULT_BLOG = Path.home() / "vaults" / "BrainSync" / "blog"

app = typer.Typer(help=__doc__, no_args_is_help=True)


PREFERRED_TALK_MODEL = "gemma4"


def default_model(provider: str) -> str | None:
    """gemma4 when installed: in a side-by-side on a real outline it was the only local model
    that sorted sentences by topic (phi4, which @best picks, assigned them in order)."""
    if provider not in ("ollama", "local"):
        return None
    from local_first_common.providers.ollama import OllamaProvider

    names = OllamaProvider()._get_installed_model_names()
    return next((n for n in names if n.startswith(PREFERRED_TALK_MODEL)), "@best")


def _save(note: Path, text: str) -> Path:
    dest = BACKUP_DIR / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S") / note.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(note, dest)
    note.write_text(text, encoding="utf-8")
    return dest


@app.command("list")
def list_notes(
    status: Annotated[str, typer.Option("--status", "-s", help="Frontmatter status to list")] = "outline",
    vault_blog: Annotated[Path, typer.Option("--vault-blog", help="Vault blog folder")] = VAULT_BLOG,
    as_json: Annotated[bool, json_option()] = False,
):
    """Post notes with a given status (default: outlines), by series and position."""
    rows = []
    for f in sorted(vault_blog.rglob("*.md")):
        if "posts" not in f.parts or f.name == "promo.md":
            continue
        fm = parse_frontmatter(f)
        if str(fm.get("status", "")).lower() != status:
            continue
        series = str(fm.get("series") or "").strip("[]")
        rows.append(
            {
                "series": series,
                "position": fm.get("series_position"),
                "target": str(fm.get("target_date") or ""),
                "path": str(f.relative_to(vault_blog)),
            }
        )
    rows.sort(key=lambda r: (r["series"], r["position"] if isinstance(r["position"], int) else 999))
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
        return
    for r in rows:
        typer.echo(f"{r['series'][:32]:32} {r['position'] or ''!s:>3}  {r['target']:10}  {r['path']}")
    typer.echo(f"{len(rows)} notes with status {status}")


@app.command("scaffold")
def scaffold_cmd(
    note: Annotated[Path, typer.Argument(help="Outline note in the vault")],
    target_words: Annotated[int, typer.Option("--target-words", "-w", help="Whole-post word target")] = 1200,
    force: Annotated[bool, typer.Option("--force", help="Scaffold even if status isn't outline")] = False,
    dry_run: Annotated[bool, dry_run_option()] = False,
):
    """Turn an outline into a drafting skeleton (status becomes draft; the outline is kept as comments)."""
    with timed_run(TOOL, None, source_location=str(note)) as run:
        try:
            text, report = scaffold(note.read_text(encoding="utf-8"), target_words, force)
        except ScaffoldError as e:
            typer.secho(f"Not scaffolded: {e}", fg=typer.colors.YELLOW)
            raise typer.Exit(1) from e
        run.item_count = 1
    if dry_run:
        typer.echo(text)
        return
    backup = _save(note, text)
    typer.echo(
        f"Scaffolded {note.name}: {report.sections} sections at ~{report.budget} words, "
        f"{report.outline_blocks} outline blocks as prompts, {len(report.fill_ins)} fill-ins, "
        f"{report.code_skipped} code blocks marked test:skip. Backup: {backup}"
    )


@app.command("talk")
def talk_cmd(
    note: Annotated[Path, typer.Argument(help="Outline or draft note in the vault")],
    recording: Annotated[Path, typer.Argument(help="Voice memo (.m4a/.wav/.mp3) or a transcript (.txt/.md)")],
    provider: Annotated[str, provider_option()] = "ollama",
    model: Annotated[str | None, model_option()] = None,
    no_scaffold: Annotated[bool, typer.Option("--no-scaffold", help="Don't scaffold an outline first")] = False,
    dry_run: Annotated[bool, dry_run_option()] = False,
):
    """Slot a spoken first draft into the note's sections, in your own words.

    The model only chooses a section for each sentence; the text is your sentences with filler removed.
    """
    text = note.read_text(encoding="utf-8")
    if not no_scaffold:
        try:
            text, _ = scaffold(text)
            typer.echo("Scaffolded the outline first.")
        except ScaffoldError:
            pass
    typer.echo(f"Reading {recording.name}...")
    transcript = read_transcript(recording)
    llm = resolve_provider(provider_name=provider, model=model or default_model(provider), tool_name=TOOL)
    llm.source_location = str(note)
    llm.item_count = 1
    new_text, report = talk(text, transcript, llm, recording.name)

    for heading, n in report.placed.items():
        typer.echo(f"  {n:3} sentences -> {heading}")
    if report.unplaced:
        typer.echo(f"  {report.unplaced:3} sentences -> {UNPLACED_HEADING}")
    if dry_run:
        typer.echo(new_text)
        return
    backup = _save(note, new_text)
    typer.echo(f"Wrote {note.name}. Backup: {backup}")
