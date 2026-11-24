"""Budget check for a day trip: plain arithmetic, so the model never adds up money itself."""

from pydantic import BaseModel, Field

from src import config
from src.errors import AppInputError


class BudgetItem(BaseModel):
    """One cost of the trip; the amount is None until the parent fills it in."""

    label: str = Field(min_length=1, max_length=80)
    amount_eur: float | None = Field(default=None, ge=0, le=config.BUDGET_RANGE_EUR[1])
    note: str = Field(default="", max_length=160)


def check_budget(budget_eur: float, items: list[BudgetItem]) -> dict:
    """Return the known total, what is left of the budget and which costs are still unknown."""
    low, high = config.BUDGET_RANGE_EUR
    if not low <= budget_eur <= high:
        raise AppInputError(f"The budget must be between {low} and {high} EUR.")
    if len(items) > config.MAX_BUDGET_ITEMS:
        raise AppInputError(f"At most {config.MAX_BUDGET_ITEMS} budget items.")
    known = [i for i in items if i.amount_eur is not None]
    unknown = [i.label for i in items if i.amount_eur is None]
    total = round(sum(i.amount_eur for i in known), 2)
    remaining = round(budget_eur - total, 2)
    if remaining < 0:
        status = "over_budget"
    elif unknown:
        status = "within_budget_so_far"
    else:
        status = "within_budget"
    return {
        "source": "Budget calculated by the app from the amounts shown below.",
        "budget_eur": round(budget_eur, 2),
        "items": [i.model_dump() for i in items],
        "known_total_eur": total,
        "remaining_eur": remaining,
        "unknown_items": unknown,
        "status": status,
    }
