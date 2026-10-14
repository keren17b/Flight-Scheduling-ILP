"""Launch from the repository root: python -m streamlit run UI/app.py."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from UI.job import CompletedResult, OptimizationJob
from UI.progress_view import render_progress
from UI.timeline import build_timeline, period, read_solution, selected_pairing, time_axis


st.set_page_config(page_title="Crew pairing", page_icon="✈", layout="wide")
st.markdown("""
<style>
@media (max-width: 950px) {
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-timeline-panel) {
    flex-direction: column;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-timeline-panel) > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important;
  }
}
</style>
""", unsafe_allow_html=True)


def reset_view():
    st.session_state.selected_id = None
    st.session_state.view_revision = st.session_state.get("view_revision", 0) + 1
    st.session_state.pop("base", None)


def chart_selection(chart_key, valid_ids):
    pid = selected_pairing(st.session_state.get(chart_key, {}), valid_ids)
    if pid:
        st.session_state.selected_id = pid


def details(pairing):
    st.subheader("Pairing details")
    st.markdown(f"**Pairing ID:** {pairing['pairing_id']}")
    st.write(f"Departure airport: {pairing['start_airport']}")
    st.write(f"Return airport: {pairing['end_airport']}")
    st.write(f"Start: {pairing['start_time']}")
    st.write(f"End: {pairing['end_time']}")
    st.write(f"Total elapsed time: {pairing['total_time']}")
    st.write(f"Cost: {pairing['cost']:.2f} sitting + rest hours")
    for index, duty in enumerate(sorted(pairing["duties"], key=lambda d: d["start_time"]), 1):
        with st.expander(f"Duty {index} · {duty['duty_id']} · {duty['start_airport']} → {duty['end_airport']}"):
            st.write(f"Origin: {duty['start_airport']} · Destination: {duty['end_airport']}")
            st.write(f"Start: {duty['start_time']} · End: {duty['end_time']}")
            st.write(f"Total elapsed time: {duty['total_time']}")
            st.dataframe([
                {"Flight ID": f["flight_id"], "Origin": f["origin"],
                 "Destination": f["destination"], "Departure": f["departure"], "Arrival": f["arrival"]}
                for f in sorted(duty["flights"], key=lambda f: f["departure"])
            ], hide_index=True, width="stretch")


def show_result(result):
    if result.data is None:
        st.warning("No run produced a feasible integer solution.")
        if result.error:
            st.error(f"Optimization failed: {result.error}")
        return
    try:
        cost, pairings = read_solution(result.data)
    except (ValueError, KeyError, TypeError) as error:
        st.error(f"Unable to display this result: {error}")
        return
    left, middle, right = st.columns([2, 1, 1])
    left.metric("Total cost · sitting + rest hours", f"{cost:,.2f}")
    middle.metric("Selected pairings", len(pairings))
    right.download_button("Download solution JSON", result.data, result.filename,
                          mime="application/json", on_click="ignore")
    if not pairings:
        st.info("The feasible solution has no selected pairings.")
        return
    bases = sorted({p["start_airport"] for p in pairings})
    base = st.selectbox("Base", ["All bases", *bases], key="base")
    visible = [p for p in pairings if base == "All bases" or p["start_airport"] == base]
    visible_ids = {p["pairing_id"] for p in visible}
    pid = st.session_state.get("selected_id")
    if pid is None:
        pid = visible[0]["pairing_id"]
        st.session_state.selected_id = pid
    chosen = next(p for p in pairings if p["pairing_id"] == pid)
    # Base filtering preserves the selected pairing and the solution's full range.
    time_range = period(pairings)
    timeline_col, detail_col = st.columns([3, 1.4], gap="large")
    with timeline_col, st.container(key="timeline-panel"):
        st.subheader("Weekly timeline")
        st.caption("Blue: duty · muted tan: rest · amber outline: selected pairing. Click a duty to select its pairing.")
        st.caption(f"{time_range[0]:%d %b %Y %H:%M} — {time_range[1]:%d %b %Y %H:%M} · {len(visible)} rows")
        st.plotly_chart(time_axis(time_range), width="stretch", theme=None,
                        config={"displayModeBar": False, "scrollZoom": False})
        chart_key = f"timeline_{st.session_state.get('view_revision', 0)}_{base}"
        with st.container(height=620, border=False):
            figure = build_timeline(visible, pid, time_range)
            st.plotly_chart(
                figure, key=chart_key, theme=None, width="stretch", height=figure.layout.height,
                on_select=lambda: chart_selection(chart_key, visible_ids), selection_mode="points",
                config={"displayModeBar": False, "scrollZoom": False},
            )
    with detail_col, st.container(key="detail-panel"):
        if pid not in visible_ids:
            st.caption("The selected pairing is outside the current base filter.")
        details(chosen)


st.title("Crew-pairing optimization")
job = st.session_state.get("job")
active = job is not None and job.snapshot()[3] is None
seed_col, count_col, button_col = st.columns([1, 1, 1], vertical_alignment="bottom")
seed = seed_col.number_input("Initial seed", value=42, step=1, disabled=active)
count = count_col.number_input("Number of runs", min_value=1, value=1, step=1, disabled=active)
if button_col.button("Run optimization", type="primary", disabled=active) and not active:
    st.session_state.completed = None
    reset_view()
    st.session_state.pop("demo_label", None)
    st.session_state.job = OptimizationJob(int(seed), int(count))
    st.session_state.job.start()
    st.rerun()


if active:
    @st.fragment(run_every=0.5)
    def monitor(expected_job):
        render_progress(expected_job)
    monitor(job)
else:
    # A full rerun can occur between worker completion and the next monitor tick.
    if job is not None:
        st.session_state.completed = job.snapshot()[3]
        st.session_state.job = None
    # Optional offline validation: explicitly chosen at launch, never automatic old results.
    if "completed" not in st.session_state and "--result" in sys.argv:
        try:
            result_path = Path(sys.argv[sys.argv.index("--result") + 1])
            data = result_path.read_bytes()
            read_solution(data)
            st.session_state.completed = CompletedResult(data, result_path.name, "integer_solution_found")
            st.session_state.demo_label = f"Saved result preview: {result_path.name} (no optimization run)"
            reset_view()
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            st.error(f"Unable to load saved result: {error}")
    if st.session_state.get("demo_label"):
        st.info(st.session_state.demo_label)
    result = st.session_state.get("completed")
    if result is not None:
        show_result(result)
