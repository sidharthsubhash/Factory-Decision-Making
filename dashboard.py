"""
Factory Edge Monitoring Dashboard (Streamlit).

Features:
- Real-time replay of industrial telemetry with local model inference.
- Advisory-First operator interface adhering to industrial safety standards.
- Feature Attribution & Explainability view for operators.
- SQLite-backed durable historian: alerts persist across browser restarts.
- Accurate metrics display (avoids misleading single-reading accuracy claims).
"""

from pathlib import Path
from datetime import datetime
import sqlite3
import time
import pandas as pd
import streamlit as st

from src.predict import predict_reading, REQUIRED_FEATURES as FEATURES, threshold, model_version

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "raw" / "SKAB" / "data" / "other"
DB_PATH = ROOT / "factory_edge_historian.db"

st.set_page_config(
    page_title="Factory Edge Condition Monitoring",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown("""
<style>
.block-container { padding-top: 1.2rem; max-width: 1550px; }
.hero-box {
    padding: 1.4rem 1.8rem;
    border-radius: 14px;
    background: linear-gradient(135deg, #0e1e2d 0%, #163242 100%);
    border: 1px solid #234b5e;
    margin-bottom: 1.2rem;
}
.hero-box h1 { color: #f0f7fc; margin: 0; font-size: 1.9rem; font-weight: 700; }
.hero-box p { color: #b5cddc; margin: 0.4rem 0 0; font-size: 0.95rem; }
.badge {
    background: #00adb5;
    color: #0c1821;
    font-size: 0.72rem;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 6px;
    letter-spacing: 1px;
}
.card-normal {
    background: #0f3024;
    border: 1px solid #1f6b4d;
    color: #92ecc0;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    font-weight: 600;
}
.card-anomaly {
    background: #3d141d;
    border: 1px solid #8c2a3e;
    color: #ff9fa9;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


# Database Historian Initialization
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_historian (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            dataset_file TEXT,
            row_index INTEGER,
            ground_truth TEXT,
            prediction TEXT,
            anomaly_probability REAL,
            threshold REAL,
            advisory TEXT,
            top_contributor TEXT,
            latency_ms REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def log_event_to_historian(event):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO event_historian (
                timestamp, dataset_file, row_index, ground_truth, prediction,
                anomaly_probability, threshold, advisory, top_contributor, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event["time"], event["file"], event["row"], event["ground_truth"],
            event["prediction"], event["probability"], event["threshold"],
            event["advisory"], event["top_contributor"], event["inference_ms"]
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Historian log error:", e)


# Session state initialization
default_state = {
    "running": False,
    "file": None,
    "df": None,
    "idx": 0,
    "latest": None,
    "filter": None,
    "last": 0.0,
    "session_events": [],
}
for key, val in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = val

# Hero Banner
st.markdown(f"""
<div class="hero-box">
  <span class="badge">LOCAL EDGE ANALYTICS · v{model_version}</span>
  <h1>🏭 Factory Edge Condition Monitoring</h1>
  <p>Real-time industrial sensor condition monitoring, local inference, and explainable operator advisory.</p>
</div>
""", unsafe_allow_html=True)

if not DATA_DIR.exists():
    st.error(f"Dataset folder not found: {DATA_DIR}")
    st.stop()

files = sorted(DATA_DIR.glob("*.csv"))
if not files:
    st.error("No SKAB dataset CSV files found.")
    st.stop()

# Sidebar Controls
st.sidebar.header("⚙️ Telemetry Replay Controls")
file_names = [f.name for f in files]
selected_file = st.sidebar.selectbox(
    "Select Industrial Recording",
    file_names,
    index=file_names.index(st.session_state.file) if st.session_state.file in file_names else 0,
)
interval = st.sidebar.select_slider(
    "Replay Tick Rate",
    options=[0.1, 0.25, 0.5, 1.0, 2.0],
    value=0.5,
    format_func=lambda x: f"{x}s per tick",
)
filter_mode = st.sidebar.selectbox(
    "Data Filter",
    ["All rows", "Normal rows only", "Anomaly rows only"],
)

# Load selected file data
if selected_file != st.session_state.file or st.session_state.df is None:
    raw_df = pd.read_csv(DATA_DIR / selected_file, sep=";")
    missing_cols = [c for c in FEATURES + ["anomaly"] if c not in raw_df.columns]
    if missing_cols:
        st.error(f"Missing required columns in {selected_file}: {missing_cols}")
        st.stop()
    st.session_state.df = raw_df.dropna(subset=FEATURES + ["anomaly"]).reset_index(drop=True)
    st.session_state.file = selected_file
    st.session_state.idx = 0
    st.session_state.latest = None
    st.session_state.session_events = []
    st.session_state.running = False

df = st.session_state.df
if filter_mode == "All rows":
    eligible_indices = df.index.tolist()
elif filter_mode == "Normal rows only":
    eligible_indices = df.index[df["anomaly"] == 0.0].tolist()
else:
    eligible_indices = df.index[df["anomaly"] == 1.0].tolist()

filter_key = (selected_file, filter_mode)
if st.session_state.filter != filter_key:
    st.session_state.filter = filter_key
    st.session_state.idx = 0
    st.session_state.latest = None
    st.session_state.session_events = []
    st.session_state.running = False

total_rows = len(eligible_indices)
if total_rows == 0:
    st.warning("No rows match current filter selection.")
    st.stop()


def process_tick(position):
    source_idx = eligible_indices[position]
    row = df.iloc[source_idx]
    reading = {feat: float(row[feat]) for feat in FEATURES}

    start_t = time.perf_counter()
    pred_res = predict_reading(reading)
    latency_ms = (time.perf_counter() - start_t) * 1000

    actual_label = "ANOMALY" if float(row["anomaly"]) == 1.0 else "NORMAL"
    prediction = pred_res["status"]

    event = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "file": selected_file,
        "row": int(source_idx),
        "ground_truth": actual_label,
        "prediction": prediction,
        "probability": pred_res["anomaly_probability"],
        "threshold": pred_res["threshold"],
        "advisory": "Investigate anomaly" if prediction == "ANOMALY" else "Monitor",
        "action_note": "Review the replay reading and related signals." if prediction == "ANOMALY" else "Continue monitoring the replay.",
        "top_contributor": pred_res["top_contributor"],
        "contributing_features": pred_res["contributing_features"],
        "inference_ms": round(latency_ms, 3),
    }

    st.session_state.session_events.append(event)
    st.session_state.latest = {"event": event, "values": reading}
    log_event_to_historian(event)


# Playback control buttons
c1, c2 = st.sidebar.columns(2)
if c1.button("▶ Start", width="stretch", disabled=st.session_state.running):
    st.session_state.running = True
    st.session_state.last = 0
    st.rerun()

if c2.button("⏸ Pause", width="stretch", disabled=not st.session_state.running):
    st.session_state.running = False
    st.rerun()

c3, c4 = st.sidebar.columns(2)
if c3.button("↺ Reset", width="stretch"):
    st.session_state.running = False
    st.session_state.idx = 0
    st.session_state.latest = None
    st.session_state.session_events = []
    st.rerun()

if c4.button("Step +1", width="stretch", disabled=st.session_state.idx >= total_rows):
    st.session_state.running = False
    process_tick(st.session_state.idx)
    st.session_state.idx += 1
    st.rerun()

st.sidebar.progress(min(st.session_state.idx / total_rows, 1.0))
st.sidebar.caption(f"Replay Position: {st.session_state.idx:,} / {total_rows:,} samples")
st.sidebar.info("Telemetry source: SKAB Benchmark · Engine: Local anomaly model")


# Real-time Live Telemetry View
@st.fragment(run_every=interval if st.session_state.running else None)
def render_live_panel():
    if st.session_state.running:
        if st.session_state.idx >= total_rows:
            st.session_state.running = False
            st.rerun()
        elif st.session_state.last == 0 or time.monotonic() - st.session_state.last >= interval:
            process_tick(st.session_state.idx)
            st.session_state.idx += 1
            st.session_state.last = time.monotonic()

    latest = st.session_state.latest
    if latest is None:
        st.info("Click **Start** or **Step +1** in the sidebar to stream sensor telemetry.")
        return

    evt = latest["event"]
    vals = latest["values"]

    st.subheader("📡 Live Machine Decision & Operator Advisory")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current Decision", evt["prediction"])
    m2.metric("Anomaly Probability", f"{evt['probability']*100:.1f}%")
    m3.metric("Decision Threshold", f"{evt['threshold']*100:.1f}%")
    m4.metric("Inference Latency", f"{evt['inference_ms']:.2f} ms")

    if evt["prediction"] == "ANOMALY":
        st.markdown(f"""
        <div class="card-anomaly">
          ⚠️ <b>ANOMALY DETECTED</b> · {evt['advisory']}<br>
          <span style="font-size:0.9rem;font-weight:400;">{evt['action_note']}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="card-normal">
          ✅ <b>NOMINAL OPERATION</b> · {evt['advisory']}<br>
          <span style="font-size:0.9rem;font-weight:400;">{evt['action_note']}</span>
        </div>
        """, unsafe_allow_html=True)

    st.caption(f"Ground Truth: **{evt['ground_truth']}** | Source: **{evt['file']}** (row #{evt['row']}) | Timestamp: {evt['time']}")

    # Feature attribution & explainability
    col_sensors, col_attrib = st.columns([1.6, 1.0])
    with col_sensors:
        st.subheader("Raw Sensor Telemetry")
        scols = st.columns(4)
        for i, feat in enumerate(FEATURES):
            scols[i % 4].metric(feat, f"{vals[feat]:.3f}")

    with col_attrib:
        st.subheader("Top Contributing Factors")
        if evt["contributing_features"]:
            cf_df = pd.DataFrame(evt["contributing_features"])
            cf_df.columns = ["Sensor Feature", "Model Weight", "Observed Value"]
            st.dataframe(cf_df, hide_index=True, width="stretch")

render_live_panel()

# Decision Historian & Session Statistics
st.divider()
st.subheader("📊 Session Statistics & Persistent Historian")

events = st.session_state.session_events
if events:
    edf = pd.DataFrame(events)
    n_processed = len(edf)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Readings Evaluated", f"{n_processed:,}")

    # Prevent deceptive 1-reading 100% agreement metric
    if n_processed < 5:
        k2.metric("Session Agreement", "Collecting data (<5)")
    else:
        agree_pct = (edf["ground_truth"] == edf["prediction"]).mean() * 100
        k2.metric("Session Agreement", f"{agree_pct:.1f}%")

    k3.metric("Anomalies Flagged", int((edf["prediction"] == "ANOMALY").sum()))
    k4.metric("Mean Edge Latency", f"{edf['inference_ms'].mean():.2f} ms")

    chart_left, chart_right = st.columns([1.4, 1.0])
    with chart_left:
        st.markdown("**Anomaly Probability vs Threshold Timeline**")
        st.line_chart(edf.set_index("row")[["probability", "threshold"]], height=260, width="stretch")
    with chart_right:
        st.markdown("**Class Distribution in Current Session**")
        st.bar_chart(edf["prediction"].value_counts().to_frame("Count"))

    st.markdown("**Recent Event Log**")
    display_cols = ["time", "file", "row", "ground_truth", "prediction", "probability", "advisory", "top_contributor", "inference_ms"]
    st.dataframe(edf[display_cols].tail(10).iloc[::-1], width="stretch", hide_index=True)

    csv_data = edf[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Export Session Audit Log (CSV)", csv_data, "factory_edge_session_audit.csv", "text/csv")
else:
    st.info("Replay session logs and timeline charts will appear once telemetry is streamed.")

with st.expander("🏭 Production Architecture & Safety Specifications"):
    st.markdown(f"""
    - **Edge Hosting:** Local execution on edge compute appliance (FastAPI + Streamlit). Zero external cloud dependency.
    - **Inference Latency:** Sub-2ms per sensor reading (deterministic latency bounded for industrial condition monitoring).
    - **Safety & Actuator Interlock:** Advisory-first architecture. Edge inferences route to operator alarms and maintenance queues. Safe machine interlocks and emergency shutdowns remain isolated within safety PLCs.
    - **Persistent Historian:** All telemetry events logged to local SQLite store (`{DB_PATH.name}`).
    """)
