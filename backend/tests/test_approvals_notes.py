from app.services.approvals import _summarize_owner_notes


def test_summarize_owner_notes_deduplicates_and_joins():
    notes = ["Site coordination", "Site coordination", "QA review completed"]
    out = _summarize_owner_notes(notes)
    assert out == "Site coordination | QA review completed"


def test_summarize_owner_notes_respects_max_len():
    out = _summarize_owner_notes(["A" * 50, "B" * 50], max_len=40)
    assert out is not None
    assert len(out) == 40
    assert out.endswith("...")
