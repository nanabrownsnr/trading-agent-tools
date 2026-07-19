from fastmcp import FastMCP
from fastmcp.apps import AppConfig
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import math
import statistics

mcp = FastMCP("computation_mcp")


class TimePoint(BaseModel):
    """
    Standard time series point format for the platform.

    The caller (DB MCP or agent) is responsible for mapping DB rows into:
        { "date": "YYYY-MM-DD", "value": float }
    """
    date: str   # "YYYY-MM-DD"
    value: float


def _parse_date(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


@mcp.tool()
def analyze_price_series(
    series: List[TimePoint],
    periods_per_year: int = 252,
) -> Dict[str, Any]:
    """
    Analyze a commodity price time series.

    Use this when:
    - You want a quick quantitative summary of price behavior over a period.
    - You want to compare different commodities or time windows.

    Args:
        series:
            List of points in the standard format:
            [
              { "date": "YYYY-MM-DD", "value": float },
              ...
            ]
            The caller is responsible for mapping DB rows into this format.
        periods_per_year:
            Number of periods per year for volatility scaling:
              - 252 for daily trading days
              - 365 for calendar days
              - 12 for monthly data, etc.

    Returns:
        {
          "start_date": str | None,
          "end_date": str | None,
          "count": int,
          "mean_price": float | None,
          "min_price": float | None,
          "max_price": float | None,
          "trend_slope_per_year": float | None,
          "annualized_volatility": float | None,
          "max_drawdown_pct": float | None
        }
    """
    if not series:
        return {
            "start_date": None,
            "end_date": None,
            "count": 0,
            "mean_price": None,
            "min_price": None,
            "max_price": None,
            "trend_slope_per_year": None,
            "annualized_volatility": None,
            "max_drawdown_pct": None,
        }

    # Sort by date
    sorted_series = sorted(series, key=lambda p: _parse_date(p.date))
    dates = [p.date for p in sorted_series]
    values = [p.value for p in sorted_series]

    # Basic stats
    clean_values = [v for v in values if v is not None and not math.isnan(v)]
    if not clean_values:
        mean_price = min_price = max_price = None
    else:
        mean_price = statistics.fmean(clean_values)
        min_price = min(clean_values)
        max_price = max(clean_values)

    # Trend: simple linear regression of price ~ time_index
    # time_index = 0, 1, 2, ... scaled to years
    n = len(values)
    if n < 2:
        trend_slope_per_year = None
    else:
        # Convert index to "years since start"
        start_dt = _parse_date(dates[0])
        xs = []
        ys = []
        for d, v in zip(dates, values):
            if v is None or math.isnan(v):
                continue
            dt = _parse_date(d)
            days = (dt - start_dt).days
            xs.append(days / 365.0)
            ys.append(v)
        if len(xs) < 2:
            trend_slope_per_year = None
        else:
            mean_x = statistics.fmean(xs)
            mean_y = statistics.fmean(ys)
            num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            den = sum((x - mean_x) ** 2 for x in xs)
            if den == 0:
                trend_slope_per_year = None
            else:
                slope = num / den  # price change per year
                trend_slope_per_year = slope

    # Returns and annualized volatility
    returns: List[float] = []
    prev = None
    for v in values:
        if prev is None or prev == 0 or v is None or math.isnan(v):
            prev = v
            continue
        r = v / prev - 1.0
        returns.append(r)
        prev = v

    if len(returns) < 2:
        annualized_vol = None
    else:
        vol = statistics.pstdev(returns)
        annualized_vol = vol * math.sqrt(periods_per_year)

    # Max drawdown
    max_drawdown_pct = None
    if clean_values:
        peak = clean_values[0]
        max_dd = 0.0
        for v in clean_values:
            if v > peak:
                peak = v
            dd = (v / peak) - 1.0
            if dd < max_dd:
                max_dd = dd
        max_drawdown_pct = max_dd  # negative number, e.g. -0.35 for -35%

    return {
        "start_date": dates[0],
        "end_date": dates[-1],
        "count": n,
        "mean_price": mean_price,
        "min_price": min_price,
        "max_price": max_price,
        "trend_slope_per_year": trend_slope_per_year,
        "annualized_volatility": annualized_vol,
        "max_drawdown_pct": max_drawdown_pct,
    }


@mcp.tool()
def compute_carrying_cost(
    quantity: float,
    price_per_unit: float,
    holding_period_days: int,
    annual_interest_rate: float = 0.08,
    annual_storage_cost_rate: float = 0.03,
    annual_insurance_cost_rate: float = 0.01,
) -> Dict[str, Any]:
    """
    Compute the carrying cost of holding a commodity position over a given period.

    Use this when:
    - You want to estimate the cost of holding inventory or a long position.
    - You want to run scenarios by changing interest, storage, or insurance rates.

    Args:
        quantity:
            Quantity held (e.g. tonnes, barrels, units).
        price_per_unit:
            Current price per unit (in the chosen currency).
        holding_period_days:
            Number of days the position is held.
        annual_interest_rate:
            Annual financing rate (default is 0.08(8%) User can provide custom value).
        annual_storage_cost_rate:
            Annual storage cost as a fraction of value (default is 0.03(3%) User can provide custom value).
        annual_insurance_cost_rate:
            Annual insurance cost as a fraction of value (default is 0.01(1%) User can provide custom value).

    Returns:
        {
          "notional_value": float,
          "interest_cost": float,
          "storage_cost": float,
          "insurance_cost": float,
          "total_carrying_cost": float,
          "carrying_cost_per_unit": float,
          "break_even_price_per_unit": float
        }
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if holding_period_days < 0:
        raise ValueError("holding_period_days cannot be negative")

    notional = quantity * price_per_unit
    period_fraction = holding_period_days / 365.0

    interest_cost = notional * annual_interest_rate * period_fraction
    storage_cost = notional * annual_storage_cost_rate * period_fraction
    insurance_cost = notional * annual_insurance_cost_rate * period_fraction

    total = interest_cost + storage_cost + insurance_cost
    per_unit = total / quantity
    break_even_price = price_per_unit + per_unit

    return {
        "notional_value": notional,
        "interest_cost": interest_cost,
        "storage_cost": storage_cost,
        "insurance_cost": insurance_cost,
        "total_carrying_cost": total,
        "carrying_cost_per_unit": per_unit,
        "break_even_price_per_unit": break_even_price,
    }



@mcp.tool()
def compute_summary_stats(series: List[float]) -> Dict[str, Any]:
    """
    Compute basic summary statistics for a numeric series.

    Use this when:
    - You want a quick overview of a price or production series.
    - You need mean, median, std, min, max.

    Args:
        series: List of numeric values.

    Returns:
        {
          "count": int,
          "mean": float | None,
          "median": float | None,
          "std": float | None,
          "min": float | None,
          "max": float | None
        }
    """

    clean = [x for x in series if x is not None and not math.isnan(x)]

    count = len(clean)
    mean = statistics.fmean(clean)
    median = statistics.median(clean)
    std = statistics.pstdev(clean) if count > 1 else 0.0
    
    return {
        "count": count,
        "mean": mean,
        "median": median,
        "std": std,
        "min": min(clean),
        "max": max(clean),
    }


middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["mcp-protocol-version", "mcp-session-id", "Authorization", "Content-Type"],
        expose_headers=["mcp-session-id"],
    )
]

app = mcp.http_app(middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
