# draft-tools

Move blog post outlines in the vault toward drafts. Neither command writes the post for
you: `scaffold` gives the outline a drafting structure, and `talk` puts your spoken words
under the right headings.

```bash
uv tool install '~/projects/local-first/draft-tools[voice]'   # [voice] adds mlx-whisper for audio

draft list                       # outlines by series and position (--status draft for drafts)
draft scaffold <note.md>         # outline -> drafting skeleton, status: draft
draft talk <note.md> memo.m4a    # spoken first draft into the note's sections
```

Every write backs the note up to `~/.local/share/draft-tools/backups/<timestamp>/` first, and
`--dry-run` prints the result instead of writing.

## scaffold

- Prose, code and tables in the outline stay as they are.
- Bullet lists become `<!-- outline: ... -->` comments: prompts to write over, then delete.
- A direct-answer slot goes under the title, and each section gets a word budget from
  `--target-words` (default 1200 for the whole post).
- Fill-in markers (`[fill ...]`, `(Fill in ...)`) are collected in a TODO comment at the top.
- Code blocks without a test annotation get `<!-- test:skip -->` (with a TODO above it).
  blog-validate starts running a post's code once it leaves `outline`, and outlines are
  full of illustrative snippets.
- `status: outline` becomes `status: draft`. Anything else is refused unless `--force`.

## talk

Record yourself explaining the post, e.g. on a walk, and pass the recording. Keep it out
of the Voice folder that voice-watcher processes, or it becomes a journal entry.

1. Audio is transcribed locally with Whisper (mlx-whisper). A `.txt`/`.md` transcript works too.
2. The transcript is split into sentences, and a local model only decides which section
   each sentence belongs to. It never writes text: the draft is your sentences, with
   filler (um, uh, "you know", "like") removed by rule.
3. Each section gets its sentences under a `<!-- spoken draft (rough) -->` marker. Asides
   and anything unassigned go under `## Spoken, not yet placed`, so nothing is dropped.

An outline is scaffolded first (`--no-scaffold` to skip). The default model is `gemma4` when
it's installed: in a side-by-side on a real outline it was the only local model that sorted
sentences by topic (phi4, which `@best` picks, assigned them in order).
