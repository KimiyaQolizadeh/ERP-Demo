from datetime import date

from app.services.ai.parser import _fallback_parse


def test_fallback_parse_handles_voice_date_range_hours_and_note():
    result = _fallback_parse(
        (
            "Create an entry for my timesheet for Project A from February 20 to February 22, "
            "billable hours, six hours. The note is inspecting the client electrical infrastructure."
        ),
        week_start=date(2026, 2, 16),
        disciplines=["Mechanical", "Electrical", "Civil", "PM"],
    )

    assert len(result.entries) == 3
    assert [entry.work_date for entry in result.entries] == [
        "2026-02-20",
        "2026-02-21",
        "2026-02-22",
    ]
    assert all(float(entry.hours) == 6.0 for entry in result.entries)
    assert all(bool(entry.billable) is True for entry in result.entries)
    assert all(
        entry.notes == "inspecting the client electrical infrastructure"
        for entry in result.entries
    )


def test_fallback_parse_distributes_total_hours_over_date_range():
    result = _fallback_parse(
        "From Feb 20 to Feb 22, total 6 hours, note is site inspection.",
        week_start=date(2026, 2, 16),
        disciplines=["Mechanical", "Electrical", "Civil", "PM"],
    )

    assert len(result.entries) == 3
    assert all(float(entry.hours) == 2.0 for entry in result.entries)
