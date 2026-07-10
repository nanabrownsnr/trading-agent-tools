# models/cost_of_carry/v1.py
from pydantic import BaseModel, Field

DESCRIPTION = "Simple cost-of-carry: spot + storage + financing over the period."

class Inputs(BaseModel):
    spot: float = Field(..., description="Current spot price")
    storage_cost: float = Field(..., description="Total storage cost over the period")
    interest_rate: float = Field(..., description="Annualized financing rate, e.g. 0.05 for 5%")
    days: int = Field(..., description="Number of days until contract expiry")

def run(inputs: Inputs) -> float:
    return inputs.spot * (1 + inputs.interest_rate * inputs.days / 365) + inputs.storage_cost