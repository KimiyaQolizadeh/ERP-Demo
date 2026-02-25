import pytest
from fastapi import HTTPException

from app.services.invoicing import _lump_sum_amount
from app.services.projects import _normalize_not_awarded_reason


def test_not_awarded_requires_reason():
    with pytest.raises(HTTPException) as exc:
        _normalize_not_awarded_reason("NOT_AWARDED", "")
    assert exc.value.status_code == 400


def test_not_awarded_reason_trimmed():
    assert _normalize_not_awarded_reason("NOT_AWARDED", "  lost bid  ") == "lost bid"


def test_non_not_awarded_reason_cleared():
    assert _normalize_not_awarded_reason("AWARDED", "some reason") is None


def test_lump_sum_amount_capped_by_remaining_contract():
    assert _lump_sum_amount(earned_value=12000, approved_budget=50000, billed_to_date=47000) == 3000


def test_lump_sum_amount_never_negative():
    assert _lump_sum_amount(earned_value=1000, approved_budget=50000, billed_to_date=51000) == 0
