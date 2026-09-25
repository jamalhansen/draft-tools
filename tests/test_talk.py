import json

from local_first_common.testing import MockProvider

from draft_tools.outline import parse_note
from draft_tools.talk import UNPLACED_HEADING, clean, split_sentences, talk

NOTE = "---\nstatus: draft\n---\n# T\n## Hook\n<!-- ~100 words -->\nExisting hook.\n## Findings\n- a bullet\n"
TRANSCRIPT = "Okay so, um, the hook. It surprised me. What I found, like, the rules held. My coffee went cold."


def _provider(assignments):
    return MockProvider(response=json.dumps({"assignments": assignments}))


def test_split_and_clean():
    assert split_sentences(TRANSCRIPT) == [
        "Okay so, um, the hook.", "It surprised me.", "What I found, like, the rules held.", "My coffee went cold."
    ]
    assert clean("So the setup was, uh, a post.") == "The setup was a post."
    assert clean("What I found, like, the rules held.") == "What I found, the rules held."


def test_sentences_land_in_their_sections_in_your_words():
    out, report = talk(NOTE, TRANSCRIPT, _provider([
        {"sentence": 1, "heading": "Hook"}, {"sentence": 2, "heading": "Hook"},
        {"sentence": 3, "heading": "findings"}, {"sentence": 4, "heading": "none"},
    ]), "memo.m4a")
    note = parse_note(out)
    hook, findings, unplaced = note.body_sections
    assert "<!-- ~100 words -->\n<!-- spoken draft (rough, from memo.m4a)" in hook.text
    assert "The hook. It surprised me.\n" in hook.text
    assert "Existing hook." in hook.text
    assert "What I found, the rules held." in findings.text
    assert unplaced.heading == UNPLACED_HEADING and "My coffee went cold." in unplaced.text
    assert report.placed == {"Hook": 2, "Findings": 1} and report.unplaced == 1


def test_model_cannot_add_or_drop_words():
    # bogus sentence numbers and unknown headings are ignored; unassigned sentences are kept
    out, report = talk(NOTE, TRANSCRIPT, _provider([
        {"sentence": 99, "heading": "Hook"}, {"sentence": 1, "heading": "Invented Section"},
    ]), "memo.m4a")
    assert report.unplaced == 4
    for s in ("The hook.", "It surprised me.", "What I found, the rules held.", "My coffee went cold."):
        assert s in out
    assert "Invented Section" not in out
