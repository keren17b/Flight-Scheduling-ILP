"""Presentation of exported records, independent of solver objects."""

from datetime import datetime, timedelta
from html import escape
import json

import plotly.graph_objects as go


BLUE = "#1261B5"
REST = "#BBA985"
HIGHLIGHT = "#FFAE00"
ROW_HEIGHT = 36
MARGINS = dict(l=125, r=24, t=12, b=12)


def timestamp(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def read_solution(data: bytes):
    """Accept combined run results and the existing standalone pairing export."""
    payload = json.loads(data)
    if "integer_solution" in payload:
        solution = payload["integer_solution"]
        if payload.get("outcome") != "integer_solution_found" or solution is None:
            raise ValueError("This result has no feasible integer solution.")
        cost, count = solution["cost"], solution["selected_pairing_count"]
    else:
        solution = payload
        cost, count = solution["total_cost"], solution["selected_count"]
    pairings = solution.get("pairings")
    if pairings is None:
        raise ValueError("This result does not contain exported pairing records.")
    if len(pairings) != count or len({p["pairing_id"] for p in pairings}) != count:
        raise ValueError("Pairing counts or IDs in the result are inconsistent.")
    return cost, sorted(pairings, key=lambda p: (timestamp(p["start_time"]), p["pairing_id"]))


def period(pairings):
    start = min(timestamp(p["start_time"]) for p in pairings)
    end = max(timestamp(p["end_time"]) for p in pairings)
    margin = max(timedelta(minutes=30), (end - start) * 0.025)
    return start - margin, end + margin


def selected_pairing(event, valid_ids):
    """Use stable IDs from actual trace customdata, never filtered row indices."""
    for point in reversed(event.get("selection", {}).get("points", [])):
        data = point.get("customdata")
        if isinstance(data, (list, tuple)) and data and data[0] in valid_ids:
            return data[0]
    return None


def time_axis(time_range):
    """A separate aligned axis stays visible above the scrolling pairing rows."""
    fig = go.Figure()
    fig.update_layout(
        height=85, margin=dict(l=125, r=24, t=5, b=50), template="plotly_white",
        paper_bgcolor="white", plot_bgcolor="white", font=dict(color="#24344A"),
        xaxis=dict(type="date", range=time_range, tickformat="%a %d %b<br>%H:%M",
                   fixedrange=True, showgrid=False),
        yaxis=dict(visible=False, fixedrange=True),
    )
    # Explicit data ensures Plotly draws the axis in an otherwise empty figure.
    fig.add_trace(go.Scatter(x=list(time_range), y=[0, 0], mode="markers", marker_opacity=0,
                             hoverinfo="skip", showlegend=False))
    return fig


def build_timeline(pairings, selected_id, time_range):
    groups = {"Duty": [], "Rest": []}
    for pairing in pairings:
        pid = pairing["pairing_id"]
        duties = sorted(pairing["duties"], key=lambda d: timestamp(d["start_time"]))
        for index, duty in enumerate(duties):
            start, end = timestamp(duty["start_time"]), timestamp(duty["end_time"])
            groups["Duty"].append((pid, start, end, [
                pid, duty["duty_id"], duty["start_airport"], duty["end_airport"],
                duty["start_time"], duty["end_time"], duty["total_time"],
                str(len(duty["flights"])), str(pairing["cost"]),
            ]))
            if index and timestamp(duties[index - 1]["end_time"]) < start:
                previous = duties[index - 1]
                rest_start = timestamp(previous["end_time"])
                groups["Rest"].append((pid, rest_start, start, [
                    pid, "Rest", previous["end_airport"], duty["start_airport"],
                    previous["end_time"], duty["start_time"], str(start - rest_start), "0",
                    str(pairing["cost"]),
                ]))
    fig = go.Figure()
    for label, color in (("Rest", REST), ("Duty", BLUE)):
        records = groups[label]
        if not records:
            continue
        # Horizontal bar traces support Plotly's native point selection.
        fig.add_trace(go.Bar(
            name=label, orientation="h", y=[r[0] for r in records],
            base=[r[1].isoformat() for r in records],
            x=[(r[2] - r[1]).total_seconds() * 1000 for r in records],
            customdata=[[r[3][0], *[escape(str(v)) for v in r[3][1:]]] for r in records],
            ids=[f"{r[0]}:{label}:{i}" for i, r in enumerate(records)],
            width=0.68 if label == "Duty" else 0.28,
            marker=dict(color=color, line=dict(
                color=[HIGHLIGHT if r[0] == selected_id else color for r in records],
                width=[3 if r[0] == selected_id else 0 for r in records],
            )),
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
            hovertemplate=(
                "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                "%{customdata[2]} → %{customdata[3]}<br>"
                "%{customdata[4]} → %{customdata[5]}<br>"
                "Elapsed: %{customdata[6]} · Flights: %{customdata[7]}<br>"
                "Pairing cost: %{customdata[8]} sitting + rest hours<extra></extra>"
            ),
        ))
    fig.update_layout(
        height=max(240, len(pairings) * ROW_HEIGHT + 24), margin=MARGINS,
        template="plotly_white", barmode="overlay", showlegend=False,
        paper_bgcolor="white", plot_bgcolor="white",
        clickmode="event+select", dragmode=False,
        xaxis=dict(type="date", range=time_range, showticklabels=False,
                   dtick=86400000, fixedrange=True),
        yaxis=dict(categoryorder="array", categoryarray=[p["pairing_id"] for p in pairings],
                   autorange="reversed", fixedrange=True, tickfont=dict(size=13)),
        font=dict(size=13, color="#24344A"),
        hoverlabel=dict(bgcolor="white", font_size=13, font_color="#24344A"),
    )
    return fig
