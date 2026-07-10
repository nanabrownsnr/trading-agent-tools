# models/cost_of_carry/v2.py
#
# Simple cost-of-carry pricing model. Designed to be tested against the
# seeded `prices` table — pull a recent spot price for Corn/Wheat/Copper
# via get_price in db-mcp, then feed it into this model as `spot`.

from pydantic import BaseModel, Field

DESCRIPTION = (
    "Cost-of-carry model: forward price = spot + storage costs + financing "
    "cost over the holding period. Suitable for physically-storable "
    "commodities (grains, metals) where the forward price is driven by the "
    "cost of holding inventory rather than expectations of future scarcity."
)


class Inputs(BaseModel):
    spot: float = Field(
        ..., gt=0,
        description="Current spot price. Use a recent value from postgres-mcp's get_price, "
                    "e.g. ~450 for Corn, ~620 for Wheat, ~9500 for Copper based on seed data."
    )
    storage_cost: float = Field(
        ..., ge=0,
        description="Total storage cost over the holding period, in the same currency unit as spot."
    )
    interest_rate: float = Field(
        ..., ge=0, le=1,
        description="Annualized financing rate as a decimal, e.g. 0.05 for 5%."
    )
    days: int = Field(
        ..., gt=0,
        description="Number of days from now until the forward/contract date."
    )


def run(inputs: Inputs) -> float:
    """forward price = spot * (1 + rate * days/365) + storage_cost"""
    return inputs.spot * (1 + inputs.interest_rate * inputs.days / 365) + inputs.storage_cost


# ---------------------------------------------------------------------------
# Quick manual test — run this file directly (python v1.py) to sanity-check
# the model in isolation, using values in the range of your seeded data,
# before testing it through the full MCP tool chain.
# ---------------------------------------------------------------------------
#if __name__ == "__main__":
    test_cases = [
        {"spot": 450.0, "storage_cost": 5.0, "interest_rate": 0.05, "days": 60},   # Corn
        {"spot": 620.0, "storage_cost": 8.0, "interest_rate": 0.05, "days": 60},   # Wheat
        {"spot": 9500.0, "storage_cost": 40.0, "interest_rate": 0.04, "days": 90}, # Copper
    ]
    for case in test_cases:
        validated = Inputs(**case)
        price = run(validated)
        print(f"inputs={case} -> forward price={price:.2f}")