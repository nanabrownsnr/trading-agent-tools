import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go

def _require_fields(df: pd.DataFrame, fields: set[str]) -> None:
    missing = fields - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected field(s) in data: {missing}")

def build_line_chart(data: list[dict], x_field: str, y_field: str,
                      series_field: str | None = None, title: str = ""):
    """
    Price/time series. Pass series_field (e.g. 'commodity') to overlay
    multiple series on one chart — e.g. Corn vs Wheat over the same range.

    Expected data shape: [{"ts": "...", "price": ..., "commodity": "Corn"}, ...]
    """
    df = pd.DataFrame(data)
    missing = {x_field, y_field} - set(df.columns)

    if missing: 
        raise ValueError(f"Missing expected field(S) in data: {missing} ")

    fig = px.line(df, x=x_field, y=y_field, color=series_field, title=title)
    return json.loads(fig.to_json())

def build_candlestick_chart(data: list[dict], x_field: str,
                             open_field: str, high_field: str,
                             low_field: str, close_field: str,
                             title: str = "") -> str:
    """
    OHLC price action. Shows range/volatility per period, not just closing price.

    Expected data shape:
        [{"ts": "...", "open": ..., "high": ..., "low": ..., "close": ...}, ...]
    """
    df = pd.DataFrame(data)
    _require_fields(df, {x_field, open_field, high_field, low_field, close_field})

    fig = go.Figure(data=[go.Candlestick(
        x=df[x_field],
        open=df[open_field],
        high=df[high_field],
        low=df[low_field],
        close=df[close_field],
    )])
    fig.update_layout(title=title, xaxis_rangeslider_visible=True)
    return json.loads(fig.to_json())

def build_dual_axis_chart(data: list[dict], x_field: str,
                           y1_field: str, y2_field: str,
                           y1_label: str | None = None, y2_label: str | None = None,
                           title: str = "") -> str:
    """
    Two variables of different scale over the same timeline on separate
    y-axes — e.g. price (left axis) vs rainfall (right axis). Useful for
    visually correlating a driver against price movement.

    Expected data shape: [{"ts": "...", "price": ..., "rainfall_mm": ...}, ...]
    """
    df = pd.DataFrame(data)
    _require_fields(df, {x_field, y1_field, y2_field})

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_field], y=df[y1_field], name=y1_label or y1_field, yaxis="y1"
    ))
    fig.add_trace(go.Scatter(
        x=df[x_field], y=df[y2_field], name=y2_label or y2_field, yaxis="y2"
    ))
    fig.update_layout(
        title=title,
        yaxis=dict(title=y1_label or y1_field),
        yaxis2=dict(title=y2_label or y2_field, overlaying="y", side="right"),
    )
    return json.loads(fig.to_json())

