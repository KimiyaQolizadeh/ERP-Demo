from types import SimpleNamespace

from app.services.invoicing import _aggregate_hours_by_discipline
from app.services.reporting import _invoice_readiness_totals


def test_invoice_aggregation_counts_only_approved_billable_uninvoiced_entries():
    rows = [
        (
            SimpleNamespace(discipline="Mechanical", hours=3.0, billable=True, invoiced_line_id=None),
            SimpleNamespace(status="APPROVED"),
        ),
        (
            SimpleNamespace(discipline="Mechanical", hours=5.0, billable=True, invoiced_line_id=None),
            SimpleNamespace(status="SUBMITTED"),
        ),
        (
            SimpleNamespace(discipline="Mechanical", hours=4.0, billable=False, invoiced_line_id=None),
            SimpleNamespace(status="APPROVED"),
        ),
        (
            SimpleNamespace(discipline="Mechanical", hours=2.0, billable=True, invoiced_line_id="line-1"),
            SimpleNamespace(status="APPROVED"),
        ),
        (
            SimpleNamespace(discipline="Electrical", hours=7.5, billable=True, invoiced_line_id=None),
            SimpleNamespace(status="APPROVED"),
        ),
    ]

    agg = _aggregate_hours_by_discipline(rows)

    assert agg == {"Mechanical": 3.0, "Electrical": 7.5}


def test_invoice_readiness_totals_move_hours_from_submitted_to_approved():
    rows = [
        (SimpleNamespace(hours=4.0), SimpleNamespace(status="SUBMITTED")),
        (SimpleNamespace(hours=6.0), SimpleNamespace(status="APPROVED")),
        (SimpleNamespace(hours=8.0), SimpleNamespace(status="DRAFT")),
    ]

    submitted_billable, approved_billable, readiness = _invoice_readiness_totals(rows)

    assert submitted_billable == 10.0
    assert approved_billable == 6.0
    assert readiness == 0.6
