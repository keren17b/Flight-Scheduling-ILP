"""Render one monitoring tick, including callbacks queued before completion."""

import streamlit as st

def render_progress(expected_job):
    current_job = st.session_state.get("job")
    # A queued fragment may outlive the job, or belong to a preceding batch.
    # Rebuild the page to remove that fragment without touching the current job.
    if current_job is None or current_job is not expected_job:
        st.rerun()
        return
    # Keep a local reference: session state is cleared when completion is handled.
    # Ignore any message field on jobs started before the display was simplified.
    _, stage, elapsed, result = current_job.snapshot()[:4]
    if result is not None:
        st.session_state.completed = result
        st.session_state.job = None
        st.rerun()
        return
    st.write(f"Current stage: {stage}")
    st.write(f"Elapsed time: {int(elapsed // 60)}m {int(elapsed % 60):02d}s")
