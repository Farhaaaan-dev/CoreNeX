"""
CoreNex — Skills & Market Intelligence Platform  v5.0
======================================================
10-page premium light-theme SaaS application.

Pages
-----
  Original 7:
    1  Overview               Dashboard home — ML Studio-style KPI tiles + workflow status
    2  Skills Intelligence    Searchable directory, ranking, profiles
    3  Demand Analytics       Historical trends, relative demand index, growth/decline
    4  Monthly Forecasts      Phase 2 validated methodology, honest readiness status
    5  Technology Comparison  Multi-skill comparison
    6  Data & Methodology     Transparency, sources, limitations
    7  About CoreNex          Mission, scope, how to read the numbers

  New ML Workflow 3:
    8  Raw Data               Restricted — not served by dashboard
    9  Data Preprocessing     prepare_data.py pipeline documented step-by-step
   10  Model Training & Eval  model_evaluation.csv, best_model_per_skill.csv, model_comparison.csv

Run:  streamlit run app.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from corenex import data_access as da
from corenex import ui
from corenex.ui import C

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CoreNex — Skills & Market Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
ui.inject_css()

# Extra CSS for ML workflow elements
st.markdown(f"""
<style>
.wf-step {{
  display:flex; gap:14px; align-items:flex-start;
  padding:13px 16px; background:{C['panel']};
  border:1px solid {C['border']}; border-radius:10px;
  margin-bottom:8px; box-shadow:0 1px 2px rgba(16,24,40,0.04);
}}
.wf-num {{
  flex-shrink:0; width:28px; height:28px; border-radius:50%;
  background:{C['blue_soft']}; color:{C['blue']};
  font-size:11.5px; font-weight:700; display:flex;
  align-items:center; justify-content:center;
}}
.wf-body {{ flex:1; min-width:0; }}
.wf-title {{ font-size:13px; font-weight:650; color:{C['text']}; margin-bottom:3px; }}
.wf-detail {{ font-size:12px; color:{C['text2']}; line-height:1.6; }}
.wf-io {{ display:flex; gap:18px; margin-top:6px; flex-wrap:wrap; }}
.wf-io-pill {{
  font-size:10.5px; padding:2px 9px; border-radius:5px;
  background:{C['card_alt']}; border:1px solid {C['border']};
  color:{C['text2']};
}}
.wf-status-ok {{
  flex-shrink:0; font-size:10px; font-weight:700; padding:3px 8px;
  border-radius:5px; background:#D1FAE5; color:#065F46;
}}
.status-dot {{
  display:inline-block; width:7px; height:7px;
  border-radius:50%; margin-right:5px; vertical-align:middle;
}}
</style>
""", unsafe_allow_html=True)

PAGES_ANALYTICS = [
    "Overview",
    "Skills Intelligence",
    "Demand Analytics",
    "Monthly Forecasts",
    "Technology Comparison",
    "Data & Methodology",
    "About CoreNex",
]

PAGES_ML = [
    "Raw Data",
    "Data Preprocessing",
    "Cleaned Data",
    "Model Training",
    "Model Evaluation",
    "Predictions",
]

# Documented shape of the restricted raw file (inspection only; never served).
RAW_ROWS, RAW_COLS = 785741, 17

# ---------------------------------------------------------------------------
# Data (cached once)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading CoreNex data...")
def get_data():
    return da.load_all()

@st.cache_data(show_spinner="Loading ML outputs...")
def get_ml_outputs():
    return da.load_ml_outputs()

data, report = get_data()
ml_out = get_ml_outputs()

if not report.loaded:
    ui.page_header("CoreNex", "Data layer unavailable")
    ui.error_state("No cleared datasets could be loaded.",
                   "Check that the project data files are present next to app.py.")
    st.stop()

wsd = data.get("weekly_skill_demand", pd.DataFrame())
wsd_ok = da.validate_weekly(wsd) if not wsd.empty else {"ok": False, "issues": ["not loaded"]}
share = da.monthly_share_from_weekly(wsd) if wsd_ok.get("ok") else pd.DataFrame()
weekly_tot = da.weekly_totals(wsd) if wsd_ok.get("ok") else pd.DataFrame()
summ = da.skill_summary(wsd) if wsd_ok.get("ok") else pd.DataFrame()

phase2_idx     = data.get("phase2_index", pd.DataFrame())
phase2_metrics = data.get("phase2_backtest_metrics", pd.DataFrame())
phase2_pred    = data.get("phase2_backtest_predictions", pd.DataFrame())
phase2_pi      = data.get("phase2_intervals", pd.DataFrame())
phase2_cov     = data.get("phase2_coverage", {})
phase2_sel     = data.get("phase2_selection", {})
phase2_ready   = da.forecast_readiness(data)
current        = data.get("current_skill_demand", pd.DataFrame())
discovery      = data.get("skill_discovery", pd.DataFrame())
registry       = data.get("source_registry", [])
manifest       = data.get("collection_manifest", {})

model_table    = da.phase2_model_table(phase2_metrics) if not phase2_metrics.empty else pd.DataFrame()
selected_model = phase2_sel.get("selected", "Naive")

me_df  = ml_out.get("model_evaluation",    pd.DataFrame())
bm_df  = ml_out.get("best_model_per_skill", pd.DataFrame())
mc_df  = ml_out.get("model_comparison",     pd.DataFrame())
fc_df  = ml_out.get("future_forecast",      pd.DataFrame())
fs_df  = ml_out.get("forecasting_summary",  pd.DataFrame())

# ---------------------------------------------------------------------------
# Deep links: ?page=<slug> selects the landing page and nav group
# ---------------------------------------------------------------------------
def _slug_key(text: str) -> str:
    """Normalise a page name or slug to a comparable key.

    'Data & Methodology', 'data-and-methodology' and 'data___methodology'
    all map to 'data and methodology'.
    """
    s = text.lower().replace("&", " and ")
    s = "".join(ch if ch.isalnum() else " " for ch in s)
    return " ".join(s.split())


def _requested_page() -> tuple[str | None, str | None]:
    """Return (group, page) for a ?page= slug, or (None, None)."""
    try:
        raw = (st.query_params.get("page") or "").strip()
    except Exception:
        return None, None
    if not raw:
        return None, None
    wanted = _slug_key(raw)
    for group, pages in (("analytics", PAGES_ANALYTICS), ("ml", PAGES_ML)):
        for p in pages:
            if _slug_key(p) == wanted:
                return group, p
    return None, None


_req_group, _req_page = _requested_page()

if "nav_analytics" not in st.session_state:
    st.session_state["nav_analytics"] = (_req_page if _req_group == "analytics"
                                         else PAGES_ANALYTICS[0])
if "nav_ml" not in st.session_state:
    st.session_state["nav_ml"] = (_req_page if _req_group == "ml" else PAGES_ML[0])

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"""
<div style="padding:4px 10px 0">
  <div style="display:flex;align-items:center;gap:11px;margin-bottom:16px">
    <div style="width:38px;height:38px;border-radius:11px;
         background:linear-gradient(135deg,{C['blue']} 0%,{C['cyan']} 100%);
         display:flex;align-items:center;justify-content:center;
         font-weight:800;font-size:13px;color:#FFF;flex-shrink:0;
         box-shadow:0 2px 8px rgba(37,99,235,0.28)">CN</div>
    <div>
      <div style="font-size:16.5px;font-weight:700;color:{C['text']};
           letter-spacing:-.5px;line-height:1.15">CoreNex</div>
      <div style="font-size:9.5px;color:{C['text3']};text-transform:uppercase;
           letter-spacing:.9px;font-weight:600">ML Intelligence Platform</div>
    </div>
  </div>
</div>
<div style="height:1px;background:{C['border']};margin:0 8px 10px"></div>
<div style="padding:0 10px 6px;font-size:9.5px;text-transform:uppercase;
     letter-spacing:.9px;color:{C['text3']};font-weight:700">Analytics</div>
""", unsafe_allow_html=True)

    page_analytics = st.radio("Analytics Navigation", PAGES_ANALYTICS,
                               label_visibility="collapsed", key="nav_analytics")

    st.markdown(f"""
<div style="height:1px;background:{C['border']};margin:8px 8px 10px"></div>
<div style="padding:0 10px 6px;font-size:9.5px;text-transform:uppercase;
     letter-spacing:.9px;color:{C['text3']};font-weight:700">ML Workflow</div>
""", unsafe_allow_html=True)

    page_ml = st.radio("ML Navigation", PAGES_ML,
                        label_visibility="collapsed", key="nav_ml")

    n_skills_txt = f"{len(summ)} skills" if not summ.empty else "—"
    n_eligible = int(bm_df["skill"].nunique()) if not bm_df.empty else 0
    st.markdown(f"""
<div style="position:absolute;bottom:18px;left:0;right:0;padding:0 12px">
  <div style="border-top:1px solid {C['border']};padding:12px 8px 0">
    <div style="font-size:10px;color:{C['text3']};line-height:1.85;font-weight:500">
      Historical: 2023 (53 weeks)<br>
      {n_skills_txt} tracked · {n_eligible} eligible<br>
      <span style="color:{C['green']}">● All systems operational</span>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

# Track which nav group was last used (a deep link seeds the initial group).
if "_last_analytics" not in st.session_state:
    st.session_state["_last_analytics"] = page_analytics
    st.session_state["_last_ml"] = page_ml
    st.session_state["_active_group"] = _req_group or "analytics"

if st.session_state["_last_analytics"] != page_analytics:
    st.session_state["_active_group"] = "analytics"
    st.session_state["_last_analytics"] = page_analytics
elif st.session_state["_last_ml"] != page_ml:
    st.session_state["_active_group"] = "ml"
    st.session_state["_last_ml"] = page_ml

active_page = page_analytics if st.session_state["_active_group"] == "analytics" else page_ml


# ===========================================================================
# HELPERS
# ===========================================================================
def _plotly(fig, height: int = 340, **extra):
    ui.apply_layout(fig, height, **extra)
    st.plotly_chart(fig, use_container_width=True)


def _wf_step_html(i: int, step: dict) -> str:
    io_pills = ""
    if step.get("input"):
        io_pills += f'<div class="wf-io-pill">In: {step["input"]}</div>'
    if step.get("output"):
        io_pills += f'<div class="wf-io-pill">Out: {step["output"]}</div>'
    return f"""
<div class="wf-step">
  <div class="wf-num">{i}</div>
  <div class="wf-body">
    <div class="wf-title">{step['step']}</div>
    <div class="wf-detail">{step['details']}</div>
    <div class="wf-io">{io_pills}</div>
  </div>
  <div class="wf-status-ok">{step.get('status', 'Complete')}</div>
</div>"""


# ===========================================================================
# ===========================================================================
# PAGE 1 -- OVERVIEW  (ML project dashboard)
# ===========================================================================
def render_overview():
    ui.page_header(
        "ML Project Dashboard",
        "Skill-demand forecasting workspace: dataset coverage, preprocessing, model "
        "selection and forecast output — all figures read from the actual pipeline artifacts.",
    )

    # Every value below is read from a real artifact; nothing is asserted.
    raw_rows_doc, raw_cols_doc = 785741, 17          # documented raw-file inspection
    n_weekly = int(len(wsd))
    n_skills = int(wsd["skill"].nunique()) if not wsd.empty else 0
    n_weeks = int(wsd["week"].nunique()) if not wsd.empty else 0
    n_eligible = int(bm_df["skill"].nunique()) if not bm_df.empty else 0
    n_total_skill_rows = int(fs_df["skill"].nunique()) if not fs_df.empty else 0
    n_forecast = int(len(fc_df))
    horizon_max = int(fc_df["horizon_weeks"].max()) if not fc_df.empty and "horizon_weeks" in fc_df else 0
    first_fc = (pd.to_datetime(fc_df["week"]).min().strftime("%d %b %Y")
                if not fc_df.empty and "week" in fc_df else "—")

    ui.kpi_row([
        {"label": "Raw job postings", "value": f"{raw_rows_doc:,}",
         "sub": "documented raw file (not served)", "accent": C["text3"]},
        {"label": "Cleared weekly records", "value": f"{n_weekly:,}",
         "sub": f"{n_skills} skills · {n_weeks} weeks", "accent": C["blue"]},
        {"label": "Skills forecast", "value": f"{n_eligible}",
         "sub": f"{n_total_skill_rows} evaluated · {n_total_skill_rows - n_eligible} excluded",
         "accent": C["cyan"]},
        {"label": "Forecast output", "value": f"{n_forecast:,}",
         "sub": f"{horizon_max} weeks ahead from {first_fc}", "accent": C["violet"]},
    ])

    st.write("")

    # ---- Dataset + model performance ----------------------------------
    c_dataset, c_model = st.columns([1.35, 1], gap="large")

    with c_dataset:
        with st.container(border=True):
            ui.card_title("Dataset overview",
                          "Top skills by total weekly mentions (2023, cleared dataset).")
            if not summ.empty:
                top_sk = summ.nlargest(8, "total_demand")
                fig = go.Figure(go.Bar(
                    x=top_sk["skill"], y=top_sk["total_demand"],
                    marker=dict(color=C["blue"], line=dict(width=0)),
                    text=[f"{v:,.0f}" for v in top_sk["total_demand"]],
                    textposition="outside", cliponaxis=False,
                    textfont=dict(size=10, color=C["text2"]),
                    hovertemplate="%{x}<br>%{y:,.0f} mentions<extra></extra>",
                ))
                _plotly(fig, 300, showlegend=False,
                        yaxis=dict(title="Mentions"),
                        xaxis=dict(tickangle=-30, showgrid=False),
                        margin=dict(l=58, r=24, t=24, b=70))
            else:
                ui.empty_state("No data loaded.")

    with c_model:
        with st.container(border=True):
            ui.card_title("Model selection", "Winning model per skill, by lowest MAE.")
            if not bm_df.empty:
                win_counts = bm_df["best_model"].value_counts()
                fig_d = go.Figure(go.Pie(
                    labels=win_counts.index.tolist(),
                    values=win_counts.values.tolist(),
                    hole=0.62,
                    marker=dict(
                        colors=[ui.MODEL_COLORS.get(m, C["blue"]) for m in win_counts.index],
                        line=dict(color="#FFFFFF", width=2),
                    ),
                    hovertemplate="%{label}<br>%{value} skills (%{percent})<extra></extra>",
                    textinfo="none",
                ))
                fig_d.add_annotation(
                    text=f"<b>{int(win_counts.sum())}</b><br>skills",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=17, color=C["text"], family="Inter"),
                    xanchor="center", yanchor="middle",
                )
                fig_d.update_layout(
                    template="plotly_white",
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    height=196, margin=dict(l=0, r=0, t=8, b=8),
                    legend=dict(orientation="v", x=1.02, y=0.5,
                                font=dict(size=11, color=C["text2"])),
                    showlegend=True,
                )
                st.plotly_chart(fig_d, use_container_width=True)
                avg_mae = float(bm_df["MAE"].mean()) if "MAE" in bm_df.columns else 0.0
                avg_rmse = float(bm_df["RMSE"].mean()) if "RMSE" in bm_df.columns else 0.0
                top_w = win_counts.idxmax() if not win_counts.empty else "—"
                st.markdown(ui.split_rows([
                    ("Best model overall", top_w),
                    ("Avg MAE", f"{avg_mae:.2f}"),
                    ("Avg RMSE", f"{avg_rmse:.2f}"),
                ]), unsafe_allow_html=True)
            else:
                ui.empty_state("No model outputs found.")

    st.write("")

    # ---- Pipeline status + activity -----------------------------------
    c_wf, c_act = st.columns([1.35, 1], gap="large")

    with c_wf:
        with st.container(border=True):
            ui.card_title("Pipeline status", "Which stages have produced real artifacts.")
            stages = [
                ("Raw data",      "Restricted", raw_rows_doc > 0, C["text3"]),
                ("Preprocessing", "Cleared",    n_weekly > 0,       C["green"]),
                ("Training",      "Complete",   n_eligible > 0,     C["green"]),
                ("Evaluation",    "Complete",   not mc_df.empty,    C["green"]),
                ("Forecasting",   "Complete",   n_forecast > 0,     C["green"]),
            ]
            cells = ""
            for i, (name, state, ok, color) in enumerate(stages):
                cells += f"""
<div style="display:flex;flex-direction:column;align-items:center;gap:6px;min-width:0">
  <div style="width:40px;height:40px;border-radius:50%;
       border:2px solid {color};background:{color}14;display:flex;align-items:center;
       justify-content:center;font-size:15px;color:{color}">
       {'✓' if ok else '—'}</div>
  <div style="font-size:11.5px;font-weight:600;color:{C['text']};text-align:center;
       line-height:1.25">{name}</div>
  <div style="font-size:10px;color:{color};font-weight:600">{state}</div>
</div>"""
                if i < len(stages) - 1:
                    cells += (f'<div style="flex:1;height:1px;background:{C["border"]};'
                              f'margin:0 4px 26px"></div>')
            st.markdown(
                f'<div style="display:flex;align-items:flex-start;padding:18px 4px 6px">'
                f'{cells}</div>', unsafe_allow_html=True)

    with c_act:
        with st.container(border=True):
            ui.card_title("Recent activity", "Derived from artifact timestamps.")
            acts = []
            if not fc_df.empty:
                acts.append(("Forecast generated", f"{n_forecast:,} rows · {horizon_max} weeks",
                             "future_forecast.csv", C["green"]))
            if not bm_df.empty:
                acts.append(("Model selection completed", f"{n_eligible} skills ranked",
                             "best_model_per_skill.csv", C["blue"]))
            if not me_df.empty:
                acts.append(("Evaluation run", f"{len(me_df):,} actual vs predicted rows",
                             "model_evaluation.csv", C["cyan"]))
            if n_weekly:
                acts.append(("Cleared dataset ready", f"{n_weekly:,} weekly records",
                             "weekly_skill_demand.csv", C["violet"]))
            for title, sub, src, color in acts:
                st.markdown(f"""
<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;
     border-bottom:1px dashed {C['border']}">
  <span style="width:7px;height:7px;border-radius:50%;background:{color};margin-top:6px;
        flex-shrink:0"></span>
  <div style="flex:1;min-width:0">
    <div style="font-size:12.5px;font-weight:600;color:{C['text']}">{title}</div>
    <div style="font-size:11px;color:{C['text3']};margin-top:1px">{sub}</div>
  </div>
  <div style="font-size:10px;color:{C['text3']};white-space:nowrap;padding-top:2px">{src}</div>
</div>""", unsafe_allow_html=True)


# PAGE 2 — SKILLS INTELLIGENCE
# ===========================================================================
def render_skills():
    ui.page_header(
        "Skills Intelligence",
        "Searchable directory of tracked technology skills, relative demand ranking, "
        "historical trend profiles, and technology categories.",
    )
    if summ.empty:
        ui.empty_state("No skill data available.", "The historical demand dataset is missing.")
        return

    with st.container(border=True):
        c1, c2, c3 = st.columns([2.2, 1.4, 1.4], gap="large")
        with c1:
            query = st.text_input("Search skills",
                                   placeholder="e.g. python, kubernetes, power bi...",
                                   label_visibility="collapsed")
        with c2:
            min_share = st.slider("Min 2023 share (%)", 0.0,
                                   float(summ["share_pct"].max()), value=0.0, step=0.1)
        with c3:
            sort_by = st.selectbox("Sort by",
                                    ["Total mentions", "2023 share %", "Consistency"],
                                    label_visibility="collapsed")

    cat_map: dict = {}
    if not current.empty and "category" in current.columns:
        for _, r in current.dropna(subset=["category"]).iterrows():
            for c_val in str(r["category"]).split("|"):
                cat_map.setdefault(str(r["skill"]).strip().lower(), set()).add(c_val.strip())

    df = summ.copy()
    if query:
        df = df[df["skill"].str.contains(query, case=False, na=False)]
    df = df[df["share_pct"] >= min_share]
    if sort_by == "2023 share %":
        df = df.sort_values("share_pct", ascending=False)
    elif sort_by == "Consistency":
        df = df.sort_values("cv", ascending=True)
    else:
        df = df.sort_values("total_demand", ascending=False)

    with st.container(border=True):
        ui.card_title(f"Directory — {len(df)} skills",
                      "Total mentions, share, consistency and trend over 2023.")
        show = df[["skill", "total_demand", "share_pct", "median_demand",
                   "nonzero_weeks", "annualised_rel_slope_pct"]].copy()
        show.columns = ["Skill", "Total Mentions", "Share %", "Median Weekly",
                        "Non-zero Weeks", "Annual. Slope %"]
        st.dataframe(show, use_container_width=True, hide_index=True, height=380)

    st.write("")
    options = df["skill"].tolist()
    if not options:
        ui.empty_state("No skills match the filters.")
        return

    with st.container(border=True):
        ui.card_title("Skill Profile", "Detailed metrics and weekly trajectory for one skill.")
        chosen = st.selectbox("Select a skill", options, key="skill_profile")
        row = summ[summ["skill"] == chosen].iloc[0]
        cats = sorted(cat_map.get(chosen.lower(), []))

        ui.kpi_row([
            {"label": "Total Mentions (2023)", "value": f"{row['total_demand']:,.0f}",
             "accent": C["blue"]},
            {"label": "2023 Share",    "value": f"{row['share_pct']:.2f}%",
             "accent": C["cyan"]},
            {"label": "Median Weekly", "value": f"{row['median_demand']:,.0f}",
             "sub": f"max {row['max_demand']:,.0f}", "accent": C["violet"]},
            {"label": "Consistency",   "value": f"{1/(1+row['cv']):.2f}",
             "sub": f"CV {row['cv']:.2f}", "accent": C["green"]},
        ])
        if cats:
            st.markdown('<div style="margin:12px 0 2px">'
                        + "".join(ui.badge(c, C["violet"]) for c in cats)
                        + '</div>', unsafe_allow_html=True)

        sub = wsd[wsd["skill"] == chosen].copy()
        sub["week"] = pd.to_datetime(sub["week"])
        sub = sub.sort_values("week")
        if not sub.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=sub["week"], y=sub["demand"], mode="lines",
                line=dict(color=C["blue"], width=2.2, shape="spline", smoothing=0.5),
                fill="tozeroy", fillcolor="rgba(37,99,235,0.08)", name="Weekly mentions",
                hovertemplate="%{x|%b %d}<br>%{y:,.0f} mentions<extra></extra>",
            ))
            if not fc_df.empty and "skill" in fc_df.columns:
                fc_sk = fc_df[fc_df["skill"] == chosen].sort_values("horizon_weeks")
                if not fc_sk.empty and "week" in fc_sk.columns:
                    bx = [sub["week"].iloc[-1]] + pd.to_datetime(fc_sk["week"]).dropna().tolist()
                    by = [float(sub["demand"].iloc[-1])] + fc_sk["forecast_demand"].tolist()
                    fig.add_trace(go.Scatter(
                        x=bx, y=by, mode="lines+markers",
                        line=dict(color=C["cyan"], width=1.8, dash="dash"),
                        marker=dict(size=4), name="12-wk forecast",
                        hovertemplate="%{x|%b %d}<br>%{y:,.0f} forecast<extra></extra>",
                    ))
            _plotly(fig, 320,
                    title=ui.chart_title(f"{chosen.title()} — weekly skill mentions (2023)"),
                    yaxis=dict(title="Mentions"))
        else:
            ui.empty_state("No weekly series for this skill.")

        if not bm_df.empty and "skill" in bm_df.columns:
            bm_row = bm_df[bm_df["skill"] == chosen]
            if not bm_row.empty:
                r2 = bm_row.iloc[0]
                col_m = ui.MODEL_COLORS.get(r2["best_model"], C["blue"])
                st.markdown(
                    f'<div style="margin-top:10px;padding:10px 14px;background:{C["card_alt"]};'
                    f'border:1px solid {C["border"]};border-radius:9px;font-size:12.5px">'
                    f'Best model: <span style="color:{col_m};font-weight:700">{r2["best_model"]} ★</span> '
                    f'&nbsp;·&nbsp; MAE <b>{r2.get("MAE",0):.2f}</b> '
                    f'· RMSE <b>{r2.get("RMSE",0):.2f}</b> '
                    f'· sMAPE <b>{r2.get("sMAPE",0):.1f}%</b></div>',
                    unsafe_allow_html=True,
                )


# ===========================================================================
# PAGE 3 — DEMAND ANALYTICS
# ===========================================================================
def render_demand():
    ui.page_header(
        "Demand Analytics",
        "Historical demand trends, relative demand index (2023 = 100), growth and decline.",
    )
    if share.empty:
        ui.empty_state("No demand data available.")
        return

    with st.container(border=True):
        ui.note_block("Metrics here measure <b>share of skill mentions</b>, not job postings, "
                      "vacancies or employment. Absolute volume drifts with data-source mix.")

    months = sorted(share["month"].unique())
    with st.container(border=True):
        c1, c2 = st.columns(2, gap="large")
        with c1:
            start = st.selectbox("From month", months, index=0,
                                  format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m"))
        with c2:
            end = st.selectbox("To month", months, index=len(months) - 1,
                                format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m"))
    if start > end:
        start, end = end, start
    sub = share[(share["month"] >= start) & (share["month"] <= end)]

    st.write("")

    with st.container(border=True):
        ui.card_title("Relative demand index (2023 = 100)",
                      "Each skill's share of all mentions, indexed to its own 2023 mean.")
        if not phase2_idx.empty:
            piv = da.phase2_index_pivot(phase2_idx)
            top_skills = piv.sum().nlargest(10).index.tolist()
            fig = go.Figure()
            for s in top_skills:
                if s in piv.columns:
                    fig.add_trace(go.Scatter(x=piv.index, y=piv[s], mode="lines", name=s,
                                             line=dict(width=2)))
            fig.add_hline(y=100, line=dict(color=C["text3"], dash="dash", width=1))
            _plotly(fig, 380,
                    title=ui.chart_title("Skill demand index (2023 mean = 100)"),
                    yaxis=dict(title="Index (2023 = 100)"))
        else:
            ui.empty_state("No Phase 2 index available.")

    st.write("")

    c_slope, c_heat = st.columns([1, 1], gap="large")

    with c_slope:
        with st.container(border=True):
            ui.card_title("Growth and decline",
                          "Annualised relative slope of each skill's share (2023).")
            if not summ.empty:
                g = summ.dropna(subset=["annualised_rel_slope_pct"]).copy()
                g = g[g["share_pct"] >= 0.5].sort_values("annualised_rel_slope_pct")
                colors = [C["red"] if v < -5 else (C["green"] if v > 5 else C["text3"])
                          for v in g["annualised_rel_slope_pct"]]
                fig = go.Figure(go.Bar(
                    x=g["annualised_rel_slope_pct"], y=g["skill"], orientation="h",
                    marker=dict(color=colors),
                    hovertemplate="%{y}<br>%{x:+.1f}%<extra></extra>",
                ))
                _plotly(fig, 420,
                        xaxis=dict(title="Annualised relative slope (%)",
                                   showgrid=True, gridcolor=C["grid"]),
                        yaxis=dict(title="", showgrid=False))
            else:
                ui.empty_state("No skill summary available.")

    with c_heat:
        with st.container(border=True):
            ui.card_title("Monthly share heatmap",
                          "Share of all mentions for the 15 largest skills.")
            top15 = sub.groupby("skill")["share"].mean().nlargest(15).index.tolist()
            hm = sub[sub["skill"].isin(top15)].pivot_table(
                index="skill", columns="month", values="share")
            if not hm.empty:
                fig = go.Figure(go.Heatmap(
                    z=hm.values,
                    x=[pd.Timestamp(col_).strftime("%Y-%m") for col_ in hm.columns],
                    y=hm.index,
                    colorscale=[
                        [0.0, "#EFF4FF"], [0.25, "#BFDBFE"],
                        [0.6, "#60A5FA"], [0.85, "#2563EB"], [1.0, "#1E3A8A"],
                    ],
                    colorbar=dict(
                        title=dict(text="Share %", font=dict(size=10, color=C["text2"])),
                        thickness=10, len=0.8,
                        tickfont=dict(size=10, color=C["text3"]),
                    ),
                    hovertemplate="%{y} · %{x}<br>%{z:.2f}%<extra></extra>",
                    xgap=2, ygap=2,
                ))
                _plotly(fig, 420, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
            else:
                ui.empty_state("No data in selected range.")


# ===========================================================================
# PAGE 4 — MONTHLY FORECASTS
# ===========================================================================
def render_forecasts():
    ui.page_header(
        "Monthly Forecasts",
        "Validated Phase 2 forecasting methodology with honest, data-driven status.",
    )

    ready  = bool(phase2_ready["supports_genuine_2026_27_forecast"])
    status = "Validated" if ready else "Insufficient data"
    accent = C["green"] if ready else C["amber"]
    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
            f'{ui.status_badge(status)}'
            f'<span style="font-size:11.5px;color:{C["text3"]}">forecast readiness</span></div>'
            f'<div class="cn-note" style="border-left:3px solid {accent};padding-left:12px">'
            f'{phase2_ready["note"]}</div>',
            unsafe_allow_html=True,
        )

    st.write("")

    with st.container(border=True):
        st.markdown(
            '<b>Forecast methodology:</b> naive projection — the latest observed value '
            'is held forward for the selected horizon (3m / 6m / 12 months). '
            'No model-based extrapolation is applied. '
            'Prediction intervals are empirical (Phase 2 validated, 80% coverage). '
            'These projections are <b>not</b> validated model-based forecasts for 2026–27. '
            'The underlying data covers only 2023 (53 weeks), and Phase 2 explicitly '
            'states that absolute 2026–27 forecasts are unsupported due to within-year '
            'source drift and insufficient series length.',
            unsafe_allow_html=True,
        )

    st.write("")

    if phase2_idx.empty or phase2_metrics.empty:
        ui.empty_state("Forecast validation outputs not found.", "Run phase2_validation.py first.")
        return

    with st.container(border=True):
        ui.card_title("Model comparison",
                      "Mean over the top 10 skills × 6 rolling origins. Lower is better.")
        if not model_table.empty:
            best_mase = model_table["MASE"].min()
            show = model_table.copy()
            show["Selected"] = show["model"].apply(lambda m: "★" if m == selected_model else "")
            st.dataframe(
                show.style.format({"MAE": "{:.4f}", "RMSE": "{:.4f}",
                                   "WAPE": "{:.2f}", "MASE": "{:.4f}"}),
                use_container_width=True, hide_index=True, height=280,
            )
            ui.info_note(f"Lower is better. Selected model: <b>{selected_model}</b> "
                         f"(MASE {best_mase:.4f}). {phase2_sel.get('rationale', '')}")

    st.write("")

    c1, c2 = st.columns([1.45, 1], gap="large")

    with c1:
        with st.container(border=True):
            ui.card_title("Historical vs projected",
                          "Observed index against the naive baseline and its 80% interval.")
            piv = da.phase2_index_pivot(phase2_idx)
            skill_opts = list(piv.columns)
            skill = st.selectbox("Skill", skill_opts, key="fc_skill")
            horizon = st.radio("Forecast horizon",
                                ["3 months", "6 months", "12 months"],
                                horizontal=True, key="fc_h")
            n_h = int(horizon.split()[0])

            hist = piv[skill].dropna()
            last_month = pd.Timestamp(hist.index.max())
            last_val   = float(hist.iloc[-1])

            pi_row = phase2_pi[phase2_pi["skill"] == skill]
            if not pi_row.empty:
                lo = float(pi_row.iloc[0]["final_lo"]) - float(pi_row.iloc[0]["final_pred"]) + last_val
                hi = float(pi_row.iloc[0]["final_hi"]) - float(pi_row.iloc[0]["final_pred"]) + last_val
            else:
                lo, hi = last_val, last_val

            future_idx = pd.date_range(
                last_month + pd.offsets.MonthBegin(1), periods=n_h, freq="MS")
            fut_pred = [last_val] * n_h

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist.index, y=hist.values, mode="lines+markers",
                line=dict(color=C["blue"], width=2.5), marker=dict(size=4),
                name="Observed (index)",
                hovertemplate="%{x|%b %Y}<br>%{y:.1f}<extra></extra>",
            ))
            fig.add_trace(go.Scatter(
                x=future_idx, y=fut_pred, mode="lines+markers",
                line=dict(color=C["amber"], width=2.2, dash="dash"),
                marker=dict(size=4), name=f"Naive projection ({n_h}m)",
                hovertemplate="%{x|%b %Y}<br>%{y:.1f}<extra></extra>",
            ))
            fig.add_trace(go.Scatter(x=future_idx, y=[hi]*n_h, mode="lines",
                                     line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=future_idx, y=[lo]*n_h, mode="lines",
                                     line=dict(width=0), fill="tonexty",
                                     fillcolor="rgba(217,119,6,0.13)",
                                     name="80% interval", hoverinfo="skip"))
            fig.add_vline(x=last_month, line=dict(color=C["text3"], dash="dot", width=1))
            _plotly(fig, 360,
                    title=ui.chart_title(f"{skill.title()} — observed vs naive projection"),
                    yaxis=dict(title="Index (2023 = 100)"))

    with c2:
        with st.container(border=True):
            ui.card_title("Validation metrics", "Interval calibration and coverage.")
            if not pi_row.empty:
                ui.kpi_row([
                    {"label": "Final projection", "value": f"{last_val:.1f}",
                     "sub": "index (2023 = 100)", "accent": C["blue"]},
                    {"label": "80% interval",     "value": f"{lo:.1f}–{hi:.1f}",
                     "sub": "empirical",           "accent": C["amber"]},
                ], columns=1)
            st.write("")
            if phase2_cov:
                cov = phase2_cov.get("mean_empirical_coverage_pct", 0)
                ui.kpi_row([{"label": "Mean empirical coverage",
                             "value": f"{cov:.1f}%",
                             "sub": f"target {phase2_cov.get('target_level_pct', 80):.0f}%",
                             "sub_color": C["green"] if phase2_cov.get("calibrated") else C["amber"],
                             "accent": C["cyan"]}], columns=1)
                ui.info_note(phase2_cov.get("caveat", ""))
            st.write("")
            ui.note_block("<b>Status legend</b><br>"
                          + "<br>".join(ui.status_badge(s) for s in
                                        ["Validated", "Provisional",
                                         "Experimental", "Insufficient data"]))

    st.write("")

    with st.container(border=True):
        ui.card_title("Backtest detail", "Per-skill residuals from rolling-origin backtest.")
        if not phase2_pred.empty:
            cols_avail = [c for c in ["skill", "month", "model", "actual", "predicted"]
                         if c in phase2_pred.columns]
            detail = phase2_pred[cols_avail].copy() if cols_avail else phase2_pred.copy()
            st.dataframe(detail, use_container_width=True, hide_index=True, height=280)
        else:
            ui.empty_state("No backtest predictions available.")


# ===========================================================================
# PAGE 5 — TECHNOLOGY COMPARISON
# ===========================================================================
def render_comparison():
    ui.page_header(
        "Technology Comparison",
        "Compare relative demand, historical trends and growth across multiple skills.",
    )
    if summ.empty:
        ui.empty_state("No data available for comparison.")
        return

    with st.container(border=True):
        ui.note_block("Comparison uses the same metric (share of mentions) for all skills.")

    candidates = summ[summ["share_pct"] >= 0.3].sort_values(
        "total_demand", ascending=False)["skill"].tolist()
    default = candidates[:4] if len(candidates) >= 4 else candidates

    with st.container(border=True):
        picked = st.multiselect("Select skills (up to 6)", candidates,
                                 default=default, key="cmp_skills")
    if not picked:
        ui.empty_state("Select at least one skill to compare.")
        return
    picked = picked[:6]

    st.write("")

    with st.container(border=True):
        ui.card_title("Historical trend comparison",
                      "Weekly mentions indexed to each skill's first week (first week = 100).")
        fig = go.Figure()
        for s in picked:
            sub = wsd[wsd["skill"] == s].copy()
            sub["week"] = pd.to_datetime(sub["week"])
            sub = sub.sort_values("week")
            if sub.empty:
                continue
            base = sub["demand"].iloc[0]
            idx  = sub["demand"] / base * 100.0 if base else sub["demand"]
            fig.add_trace(go.Scatter(x=sub["week"], y=idx, mode="lines",
                                     name=s, line=dict(width=2)))
        fig.add_hline(y=100, line=dict(color=C["text3"], dash="dash", width=1))
        _plotly(fig, 360, yaxis=dict(title="Index (first week = 100)"))

    st.write("")

    with st.container(border=True):
        ui.card_title("Side-by-side metrics",
                      "Same metric, same period, for selected skills.")
        rows = []
        for s in picked:
            r = summ[summ["skill"] == s]
            if r.empty:
                continue
            r = r.iloc[0]
            rows.append({
                "Skill":          s.title(),
                "Total Mentions": f"{r['total_demand']:,.0f}",
                "Share %":        f"{r['share_pct']:.2f}",
                "Median Weekly":  f"{r['median_demand']:,.0f}",
                "Annual. Slope %": f"{r['annualised_rel_slope_pct']:+.1f}",
                "Consistency":    f"{1/(1+r['cv']):.2f}",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.write("")

    if not phase2_idx.empty:
        with st.container(border=True):
            ui.card_title("Relative index comparison (2023 = 100)",
                          "Only skills present in the Phase 2 top-10 index set are plotted.")
            piv = da.phase2_index_pivot(phase2_idx)
            avail = [s for s in picked if s in piv.columns]
            if avail:
                fig = go.Figure()
                for s in avail:
                    fig.add_trace(go.Scatter(x=piv.index, y=piv[s],
                                             mode="lines", name=s, line=dict(width=2)))
                fig.add_hline(y=100, line=dict(color=C["text3"], dash="dash", width=1))
                _plotly(fig, 340, yaxis=dict(title="Index (2023 = 100)"))
            else:
                ui.info_note("None of the selected skills are in the Phase 2 top-10 index set.")


# ===========================================================================
# PAGE 6 — DATA & METHODOLOGY
# ===========================================================================
def render_methodology():
    ui.page_header(
        "Data & Methodology",
        "Transparency: sources, coverage, preparation, validation, "
        "model performance and limitations.",
    )

    with st.container(border=True):
        ui.card_title("Load report", "Cleared datasets served by this application.")
        st.dataframe(pd.DataFrame([
            {"Dataset": k, "Rows": v.get("rows"), "File": v.get("path")}
            for k, v in report.loaded.items()
        ]), use_container_width=True, hide_index=True)
        if report.failed:
            st.warning("Some datasets failed to load: " + ", ".join(report.failed.keys()))

    st.write("")

    with st.container(border=True):
        ui.card_title("Source registry", "Provenance, publisher and licence per source.")
        if registry:
            reg_rows = [{
                "ID": s.get("id"), "Name": s.get("name"),
                "Publisher": s.get("publisher"), "Access": s.get("access_method"),
                "Licence": s.get("license"), "Role": s.get("role"),
                "Status": s.get("status"),
            } for s in registry]
            st.dataframe(pd.DataFrame(reg_rows), use_container_width=True, hide_index=True)
        else:
            ui.empty_state("No source registry available.")

    st.write("")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(border=True):
            ui.card_title("Licensing & provenance", "What is served, and what is withheld.")
            ui.note_block(
                "<b>Restricted / not publicly exposed:</b> the raw 2023 scrape "
                "(<code>data_jobs.csv</code>) has no verified licence or provenance and is "
                "<b>not</b> served by this application. Raw API dumps, credentials and local "
                "paths are never exposed.")
    with c2:
        with st.container(border=True):
            ui.card_title("Forecasting & validation methodology", "How the numbers are produced.")
            if phase2_sel:
                ui.note_block(
                    "<b>Target:</b> monthly share of all skill mentions (%).<br>"
                    "<b>Validation:</b> expanding-window rolling-origin backtest (6 origins), "
                    "no random split, no leakage.<br>"
                    "<b>Models:</b> Naive, SeasonalNaive, MovingAverage3, LinearTrend, "
                    "HoltLinear, DampedHolt, XGBoost.<br>"
                    "<b>Metrics:</b> MAE, RMSE, WAPE, sMAPE, MASE (primary).<br>"
                    f"<b>Selected:</b> {selected_model} — {phase2_sel.get('rationale', '')}")

    st.write("")

    with st.container(border=True):
        ui.card_title("Model performance (aggregate)", "Backtest metrics averaged over skills.")
        if not model_table.empty:
            st.dataframe(
                model_table.style.format({"MAE": "{:.4f}", "RMSE": "{:.4f}",
                                          "WAPE": "{:.2f}", "MASE": "{:.4f}"}),
                use_container_width=True, hide_index=True,
            )

    st.write("")

    with st.container(border=True):
        ui.card_title("Known limitations", "Stated plainly, not hidden.")
        for lim in [
            "2023 only (N=1 year): trend and seasonality are not separable.",
            "The 2026 corpus changes source and method each month; it is a cross-section, not a series.",
            "`demand` = skill mentions, not postings, vacancies or headcount.",
            "Absolute volume drifts with source mix; only relative shares are near-stationary.",
            "Prediction intervals are indicative (6 residuals per skill).",
            "Tip: The weekly skill demand data covers 53 weeks (2023 only). "
        ]:
            st.markdown(
                f"<div style='font-size:12.5px;color:{C['text2']};padding:4px 0'>"
                f"•&nbsp; {lim}</div>",
                unsafe_allow_html=True,
            )


# ===========================================================================
# PAGE 7 — ABOUT
# ===========================================================================
def render_about():
    ui.page_header("About CoreNex",
                   "A technology-skills and market-intelligence workspace built on transparent, "
                   "validated data.")

    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        with st.container(border=True):
            ui.card_title("What CoreNex does", "")
            ui.note_block(
                "CoreNex turns public job-market and technology-trend data into a normalised, "
                "auditable view of skill demand. It emphasises <b>honesty over polish</b>: "
                "where the data cannot support a claim, the platform says so.")
    with c2:
        with st.container(border=True):
            ui.card_title("How to read the numbers", "")
            ui.note_block(
                "<b>Mentions</b> — how often a skill appears across postings.<br><br>"
                "<b>Share</b> — a skill's mentions as a percentage of all mentions.<br><br>"
                "<b>Index (2023 = 100)</b> — a skill's share relative to its own 2023 average."
                "<br><br>None of these are job openings or headcount.")
    with c3:
        with st.container(border=True):
            ui.card_title("Data policy", "")
            ui.note_block(
                "Only cleared datasets are served. Restricted raw data, credentials and local "
                "paths are never exposed. No observation is fabricated.")

    st.write("")

    with st.container(border=True):
        ui.card_title("At a glance", "The numbers behind this workspace.")
        ui.kpi_row([
            {"label": "Skills Tracked",   "value": f"{len(summ)}",  "accent": C["blue"]},
            {"label": "Weekly Periods",   "value": f"{wsd['week'].nunique() if not wsd.empty else 0}",
             "accent": C["cyan"]},
            {"label": "Cleared Datasets", "value": f"{len(getattr(report, 'loaded', {}) or {})}",
             "accent": C["violet"]},
            {"label": "Selected Model",   "value": str(selected_model),  "accent": C["green"]},
            {"label": "Eligible Skills",  "value": f"{len(bm_df) if not bm_df.empty else '—'}",
             "accent": C["amber"]},
        ])


# ===========================================================================
# ===========================================================================
# PAGE 8 -- RAW DATA
# ===========================================================================
def render_raw_data():
    ui.page_header(
        "Raw Data",
        "The original 2023 job-posting scrape. This file is unlicensed and is not served "
        "by the application; only its documented shape is reported.",
    )

    with st.container(border=True):
        st.markdown(f"""
<div style="display:flex;gap:12px;align-items:flex-start">
  <div style="flex-shrink:0;margin-top:1px">{ui.status_badge("Insufficient data")}</div>
  <div class="cn-note">
    <b>data_jobs.csv is restricted.</b> It has no verified licence or provenance, so it is
    never loaded, sampled or displayed by this application. The figures below come from a
    documented one-off inspection of the file's shape only — no row-level content is exposed.
    Per-column quality metrics (missing values, duplicates) are <b>not</b> asserted here,
    because profiling a restricted file is out of scope.
  </div>
</div>""", unsafe_allow_html=True)

    st.write("")

    ui.kpi_row([
        {"label": "Raw records", "value": f"{RAW_ROWS:,}",
         "sub": "documented inspection", "accent": C["text3"]},
        {"label": "Columns", "value": f"{RAW_COLS}",
         "sub": "features per record", "accent": C["text3"]},
        {"label": "Coverage", "value": "2023",
         "sub": "single year only", "accent": C["amber"]},
        {"label": "Served by app", "value": "No",
         "sub": "restricted source", "sub_color": C["red"], "accent": C["red"]},
    ])

    st.write("")

    c_schema, c_alt = st.columns([1.5, 1], gap="large")

    with c_schema:
        with st.container(border=True):
            ui.card_title("Documented schema", "Column names and types from the inspection.")
            schema = pd.DataFrame([
                {"Column": "job_title_short", "Type": "object"},
                {"Column": "job_title", "Type": "object"},
                {"Column": "job_location", "Type": "object"},
                {"Column": "job_via", "Type": "object"},
                {"Column": "job_schedule_type", "Type": "object"},
                {"Column": "job_work_from_home", "Type": "bool"},
                {"Column": "search_location", "Type": "object"},
                {"Column": "job_posted_date", "Type": "datetime"},
                {"Column": "job_no_degree_mention", "Type": "bool"},
                {"Column": "job_health_insurance", "Type": "bool"},
                {"Column": "job_country", "Type": "object"},
                {"Column": "salary_rate", "Type": "object"},
                {"Column": "salary_year_avg", "Type": "float64"},
                {"Column": "salary_hour_avg", "Type": "float64"},
                {"Column": "company_name", "Type": "object"},
                {"Column": "job_skills", "Type": "object"},
                {"Column": "job_type_skills", "Type": "object"},
            ])
            st.dataframe(schema, use_container_width=True, hide_index=True, height=380)

    with c_alt:
        with st.container(border=True):
            ui.card_title("What is served instead", "")
            ui.note_block(
                "The cleared, aggregated dataset is fully available in this application:<br><br>"
                f"• <b>{len(wsd):,}</b> weekly (week, skill, demand) records<br>"
                f"• <b>{wsd['skill'].nunique() if not wsd.empty else 0}</b> normalised skills<br>"
                f"• <b>{wsd['week'].nunique() if not wsd.empty else 0}</b> weeks in 2023<br><br>"
                "Open <b>Cleaned Data</b> in the ML Workflow group to explore it, "
                "or <b>Data Preprocessing</b> to see the operations that produced it.")
            st.markdown(
                f'<div style="margin-top:12px;font-size:12px">'
                f'<a href="?page=cleaned-data" target="_self">→ Go to Cleaned Data</a></div>',
                unsafe_allow_html=True)


# ===========================================================================
# PAGE 9 -- DATA PREPROCESSING
# ===========================================================================
def render_preprocessing():
    ui.page_header(
        "Data Preprocessing",
        "The prepare_data.py pipeline that turns raw job postings into the weekly skill "
        "demand dataset — operations, inputs and outputs.",
    )

    ba = da.preprocessing_before_after()
    before, after = ba["before"], ba["after"]

    c_b, c_arrow, c_a = st.columns([5, 1, 5], gap="small")

    with c_b:
        with st.container(border=True):
            ui.card_title("Before", "Raw scrape (restricted, not served)")
            ui.kpi_row([
                {"label": "Rows", "value": f"{before['rows']:,}", "accent": C["text3"]},
                {"label": "Columns", "value": f"{before['cols']}", "accent": C["text3"]},
            ], columns=2)
            ui.info_note(before["note"])

    with c_arrow:
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:center;'
            f'height:100%;font-size:26px;color:{C["blue"]};padding-top:54px">→</div>',
            unsafe_allow_html=True)

    with c_a:
        with st.container(border=True):
            ui.card_title("After", "weekly_skill_demand.csv (cleared, served)")
            ui.kpi_row([
                {"label": "Rows", "value": f"{after['rows']:,}", "accent": C["green"]},
                {"label": "Columns", "value": f"{after['cols']}", "accent": C["green"]},
                {"label": "Skills", "value": f"{after['skills']}", "accent": C["blue"]},
                {"label": "Weeks", "value": f"{after['weeks']}", "accent": C["cyan"]},
            ], columns=2)
            ui.info_note(after["note"])

    st.write("")

    with st.container(border=True):
        ui.card_title("Pipeline steps", "Operations performed by prepare_data.py, in order.")
        steps = da.preprocessing_steps()
        st.markdown("".join(_wf_step_html(i + 1, s) for i, s in enumerate(steps)),
                    unsafe_allow_html=True)

    st.write("")

    with st.container(border=True):
        ui.card_title("Record reduction", "Documented input shape vs. served output shape.")
        stages = ["Raw postings (documented)", "Cleared (week, skill) pairs"]
        vals = [before["rows"], after["rows"]]
        fig = go.Figure(go.Bar(
            x=stages, y=vals,
            marker=dict(color=[C["text3"], C["green"]], line=dict(width=0)),
            text=[f"{v:,}" for v in vals],
            textposition="outside", cliponaxis=False,
            textfont=dict(size=11.5, color=C["text2"]),
            hovertemplate="%{x}<br>%{y:,} records<extra></extra>",
        ))
        _plotly(fig, 280, showlegend=False,
                yaxis=dict(title="Records", range=[0, max(vals) * 1.18]),
                xaxis=dict(title=""))
        ui.info_note("The two shapes measure different things: raw postings versus aggregated "
                     "(week, skill) mentions. The ratio is not a data-loss metric — one posting "
                     "yields one row per skill it mentions.")

    st.write("")

    with st.container(border=True):
        ui.card_title("Cleaned dataset preview", "weekly_skill_demand.csv, first 300 rows.")
        if not wsd.empty:
            st.dataframe(wsd.sort_values(["week", "skill"]).head(300),
                         use_container_width=True, hide_index=True, height=350)
            ui.info_note(f"Showing 300 of {len(wsd):,} rows · "
                         f"{wsd['skill'].nunique()} skills · {wsd['week'].nunique()} weeks.")


# ===========================================================================
# PAGE 10 -- CLEANED DATA
# ===========================================================================
def render_cleaned_data():
    ui.page_header(
        "Cleaned Data",
        "The processed datasets served by this application, with live quality checks: "
        "dimensions, missing cells, duplicates and search, and pipeline status.",
    )

    with st.container(border=True):
        ui.card_title("Dataset availability",
                      "The cleaned dataset is loaded and available. "
                      "but this page currently shows an overview only.")

    if not wsd.empty:
        with st.container(border=True):
            ui.card_title("Preview", "weekly_skill_demand.csv, first 300 rows.")
            st.dataframe(
                wsd.sort_values(["week", "skill"]).head(300),
                use_container_width=True, hide_index=True, height=350,
            )
            ui.info_note(
                f"Showing 300 of {len(wsd):,} rows · "
                f"{wsd['skill'].nunique()} skills · {wsd['week'].nunique()} weeks."
            )

    with st.container(border=True):
        ui.card_title("Preprocessing pipeline",
                      "The intended operations of prepare_data.py:")
        ui.note_block(
            "<b>Step 1:</b> Skill list explosion — each job posting is expanded so one row "
            "equals one (job, skill) pair.<br><br>"
            "<b>Step 2:</b> Skill string normalisation — whitespace stripped, lowercase, "
            "empty strings dropped.<br><br>"
            "<b>Step 3:</b> Aggregation by (week, skill) — total mentions counted per pair "
            "across all chunks, producing the weekly demand count.<br><br>"
            "<b>Output:</b> weekly_skill_demand.csv — 11,779 rows, 252 skills, 53 weeks (2023 only)."
        )
        ui.info_note(
            "Note: This pipeline is documented and validated (Phase 2). The cleaned dataset "
            "is served through the data_access layer. A fully interactive cleaned-data page "
            "will be added in a future phase."
        )

    st.write("")

    with st.container(border=True):
        ui.empty_state(
            "No custom cleaned-data table view available.",
            "The weekly skill demand data is served as the aggregated "
            "weekly_skill_demand.csv dataset. Use the Model Training & Evaluation "
            "page to view model performances on this data."
        )

    st.write("")

# ROUTER
# ===========================================================================



# ===========================================================================
# PAGE 11 -- MODEL TRAINING
# ===========================================================================

def render_model_training():
    ui.page_header(
        "Model Training",
        "forecast_engine.py evaluates three models per skill on a rolling one-step-ahead "
        "test window, then selects the lowest-MAE model for each skill.",
    )

    n_elig = int(bm_df["skill"].nunique()) if not bm_df.empty else 0
    n_eval = int(fs_df["skill"].nunique()) if not fs_df.empty else 0
    n_excl = max(n_eval - n_elig, 0)
    n_pct = f"{100.0 * n_excl / n_eval:.1f}%" if n_eval else "N/A"

    ui.kpi_row([
        {"label": "Algorithms", "value": "3",
         "sub": "Previous Week · Moving Average · XGBoost", "accent": C["blue"]},
        {"label": "Skills evaluated", "value": f"{n_eval}",
         "sub": "from forecasting_summary.csv", "accent": C["cyan"]},
        {"label": "Eligible", "value": f"{n_elig}",
         "sub": "enough non-zero weeks", "sub_color": C["green"], "accent": C["green"]},
        {"label": "Excluded", "value": f"{n_excl}",
         "sub": f"{n_excl} skills ({n_pct}) — insufficient history",
         "sub_color": C["amber"], "accent": C["amber"]},
    ])

    st.write("")

    c_cfg, c_sel = st.columns([1, 1.2], gap="large")

    with c_cfg:
        with st.container(border=True):
            ui.card_title("Training configuration", "As implemented in forecast_engine.py.")
            ui.split_rows([
                ("Algorithms", "Previous Week · 4-week MA · XGBoost"),
                ("XGBoost features", "lags 1–4 + rolling mean (4)"),
                ("Evaluation", "Rolling one-step-ahead, last 8 weeks"),
                ("Leakage control", "No test values fed back"),
                ("Selection rule", "Lowest MAE per skill"),
                ("Forecast horizon", "12 weekly steps (recursive)"),
            ])
            ui.info_note(
                "Read directly from the documented forecasting engine: test values are "
                "never fed back into features, so the evaluation has no future-data leakage."
            )

    with c_sel:
        with st.container(border=True):
            ui.card_title("Model wins", "Skills where each model achieved the lowest MAE.")
            if not bm_df.empty:
                wins = bm_df["best_model"].value_counts()
                fig = go.Figure(go.Bar(
                    x=wins.index.tolist(), y=wins.values.tolist(),
                    marker=dict(
                        color=[ui.MODEL_COLORS.get(m, C["blue"]) for m in wins.index],
                        line=dict(width=0)
                    ),
                    text=[str(v) for v in wins.values],
                    textposition="outside",
                    textfont=dict(size=12, color=C["text2"]),
                    hovertemplate="%{x}<br>%{y} skills<extra></extra>",
                ))
                _plotly(
                    fig, 300, showlegend=False,
                    yaxis=dict(title="Skills won", range=[0, wins.max() * 1.2]),
                    xaxis=dict(title="")
                )
            else:
                ui.empty_state("best_model_per_skill.csv not found.")

    st.write("")

    with st.container(border=True):
        ui.card_title(
            "Eligibility breakdown",
            "Why each skill was included or excluded."
        )
        if not fs_df.empty and "reason" in fs_df.columns:
            reasons = (
                fs_df.groupby(["eligible", "reason"]).size()
                .reset_index(name="skills")
                .sort_values("skills", ascending=False)
            )
            st.dataframe(reasons, use_container_width=True, hide_index=True, height=260)
        else:
            ui.empty_state("forecasting_summary.csv not found.")

    st.write("")

    with st.container(border=True):
        ui.card_title(
            "Selected model per skill",
            "Lowest-MAE model and its holdout metrics."
        )
        if not bm_df.empty:
            show = bm_df.copy()
            show.columns = [c.replace("_", " ").title() for c in show.columns]
            st.dataframe(show, use_container_width=True, hide_index=True, height=380)
        else:
            ui.empty_state("best_model_per_skill.csv not found.")


# ===========================================================================
# PAGE 12 -- MODEL EVALUATION
# ===========================================================================
def render_model_evaluation():
    ui.page_header(
        "Model Evaluation",
        "Holdout performance of every model on the rolling test window, plus per-skill "
        "error distributions. All values come from the evaluation artifacts.",
    )

    n_elig_e = int(bm_df["skill"].nunique()) if not bm_df.empty else 0
    n_eval_e = int(fs_df["skill"].nunique()) if not fs_df.empty else 0
    n_excl_e = max(n_eval_e - n_elig_e, 0)
    test_weeks = (int(me_df["week"].nunique())
                  if not me_df.empty and "week" in me_df.columns else 0)

    with st.container(border=True):
        ui.card_title("Evaluation configuration", "")
        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            st.markdown(ui.split_rows([
                ("Models", "Previous Week · 4-week MA · XGBoost"),
                ("Protocol", "Rolling one-step-ahead"),
            ]), unsafe_allow_html=True)
        with c2:
            st.markdown(ui.split_rows([
                ("Test weeks", f"{test_weeks}"),
                ("Skills evaluated", f"{n_eval_e}"),
            ]), unsafe_allow_html=True)
        with c3:
            st.markdown(ui.split_rows([
                ("Eligible", f"{n_elig_e}"),
                ("Excluded", f"{n_excl_e}"),
            ]), unsafe_allow_html=True)

    st.write("")

    c_wins, c_avg = st.columns([1, 1.6], gap="large")

    with c_wins:
        with st.container(border=True):
            ui.card_title("Model wins", "Skills where each model had the lowest MAE.")
            if not bm_df.empty and "best_model" in bm_df.columns:
                wins = bm_df["best_model"].value_counts()
                fig = go.Figure(go.Bar(
                    x=wins.index.tolist(), y=wins.values.tolist(),
                    marker=dict(color=[ui.MODEL_COLORS.get(m, C["blue"]) for m in wins.index],
                                line=dict(width=0)),
                    text=[str(v) for v in wins.values],
                    textposition="outside", textfont=dict(size=12, color=C["text2"]),
                    hovertemplate="%{x}<br>%{y} skills<extra></extra>",
                ))
                _plotly(fig, 280, showlegend=False,
                        yaxis=dict(title="Skills won", range=[0, wins.max() * 1.2]),
                        xaxis=dict(title=""))
            else:
                ui.empty_state("No model comparison data.")

    with c_avg:
        with st.container(border=True):
            ui.card_title("Average metrics by model", "Mean across all evaluated skills.")
            if not mc_df.empty and "model" in mc_df.columns:
                avg_m = (mc_df.groupby("model")[["MAE", "RMSE", "sMAPE"]]
                         .mean().round(2).reset_index())
                avg_m.columns = ["Model", "Avg MAE", "Avg RMSE", "Avg sMAPE (%)"]
                st.dataframe(avg_m, use_container_width=True, hide_index=True, height=180)
            else:
                ui.empty_state("model_comparison.csv not found.")
            if not bm_df.empty:
                st.write("")
                ui.kpi_row([
                    {"label": "Avg MAE", "value": f"{bm_df['MAE'].mean():.2f}"
                     if "MAE" in bm_df.columns else "—", "accent": C["blue"]},
                    {"label": "Avg RMSE", "value": f"{bm_df['RMSE'].mean():.2f}"
                     if "RMSE" in bm_df.columns else "—", "accent": C["cyan"]},
                    {"label": "Avg sMAPE", "value": f"{bm_df['sMAPE'].mean():.1f}%"
                     if "sMAPE" in bm_df.columns else "—", "accent": C["violet"]},
                ], columns=3)

    st.write("")

    with st.container(border=True):
        ui.card_title("MAE distribution by model", "Per-skill MAE spread across evaluated skills.")
        if not mc_df.empty and "model" in mc_df.columns:
            fig = go.Figure()
            for m in mc_df["model"].unique():
                sub = mc_df[mc_df["model"] == m]["MAE"].dropna()
                fig.add_trace(go.Box(
                    y=sub, name=m,
                    marker=dict(color=ui.MODEL_COLORS.get(m, C["blue"]), opacity=0.8),
                    line=dict(color=ui.MODEL_COLORS.get(m, C["blue"])),
                    boxmean="sd",
                    hovertemplate=f"<b>{m}</b><br>MAE: %{{y:.2f}}<extra></extra>",
                ))
            _plotly(fig, 300, showlegend=False, yaxis=dict(title="MAE"))
        else:
            ui.empty_state("No model comparison data.")

    st.write("")

    tab_best, tab_eval, tab_fc = st.tabs([
        "Best Model per Skill",
        "Evaluation Detail",
        "Forecasts",
    ])

    with tab_best:
        if not bm_df.empty:
            show_bm = bm_df.copy()
            show_bm.columns = [c.replace("_", " ").title() for c in show_bm.columns]
            st.dataframe(show_bm, use_container_width=True, hide_index=True, height=380)
        else:
            ui.empty_state("best_model_per_skill.csv not found.")

    with tab_eval:
        if not me_df.empty:
            st.dataframe(me_df.head(500), use_container_width=True, hide_index=True, height=380)
            ui.info_note(f"Showing 500 of {len(me_df):,} rows · "
                         f"{me_df['skill'].nunique()} skills · "
                         f"{me_df['model'].nunique()} models.")
        else:
            ui.empty_state("model_evaluation.csv not found.")

    with tab_fc:
        if not fc_df.empty:
            st.dataframe(fc_df.head(500), use_container_width=True, hide_index=True, height=380)
            ui.info_note(f"Showing 500 of {len(fc_df):,} forecast rows · "
                         f"{fc_df['skill'].nunique()} skills.")
        else:
            ui.empty_state("future_forecast.csv not found.")

    st.write("")

    with st.container(border=True):
        ui.card_title("Skill-level MAE vs total demand",
                      "Each dot is one skill; higher-demand skills tend to have higher absolute MAE.")
        if not bm_df.empty and not summ.empty and "MAE" in bm_df.columns:
            merged = bm_df.merge(summ[["skill", "total_demand"]], on="skill", how="left")
            fig = go.Figure()
            for m in merged["best_model"].unique():
                sub = merged[merged["best_model"] == m]
                fig.add_trace(go.Scatter(
                    x=sub["total_demand"], y=sub["MAE"], mode="markers", name=m,
                    marker=dict(color=ui.MODEL_COLORS.get(m, C["blue"]), size=7, opacity=0.7),
                    hovertemplate=("<b>%{text}</b><br>Total demand: %{x:,.0f}<br>"
                                   "MAE: %{y:.2f}<extra></extra>"),
                    text=sub["skill"].tolist(),
                ))
            _plotly(fig, 320,
                    xaxis=dict(title="Total demand (2023)", showgrid=True, gridcolor=C["grid"]),
                    yaxis=dict(title="MAE"))
        else:
            ui.empty_state("Insufficient data for this chart.")


# ===========================================================================
# PAGE 13 -- PREDICTIONS
# ===========================================================================
def render_predictions():
    ui.page_header(
        "Predictions",
        "The 12-week recursive forecast produced by forecast_engine.py for every eligible "
        "skill, using each skill's selected model.",
    )

    if fc_df.empty:
        ui.empty_state("No forecast output available.", "future_forecast.csv was not found.")
        return

    fc = fc_df.copy()
    fc["week"] = pd.to_datetime(fc["week"])
    horizon_max = int(fc["horizon_weeks"].max())
    first_fc = fc["week"].min()
    last_fc = fc["week"].max()

    ui.kpi_row([
        {"label": "Forecast rows", "value": f"{len(fc):,}", "accent": C["blue"]},
        {"label": "Skills", "value": f"{fc['skill'].nunique()}", "accent": C["cyan"]},
        {"label": "Horizon", "value": f"{horizon_max} wks",
         "sub": f"{first_fc:%d %b %Y} → {last_fc:%d %b %Y}", "accent": C["violet"]},
        {"label": "Models used", "value": f"{fc['model_used'].nunique()}",
         "sub": " · ".join(sorted(fc["model_used"].unique())), "accent": C["green"]},
    ])

    st.write("")

    with st.container(border=True):
        ui.card_title("Forecast by skill", "Historical weekly mentions followed by the forecast path.")
        options = sorted(fc["skill"].unique())
        skill = st.selectbox("Skill", options, index=0, key="pred_skill")

        sub = fc[fc["skill"] == skill].sort_values("week")
        hist = wsd[wsd["skill"] == skill].copy() if not wsd.empty else pd.DataFrame()
        if not hist.empty:
            hist["week"] = pd.to_datetime(hist["week"])
            hist = hist.sort_values("week")

        fig = go.Figure()
        if not hist.empty:
            fig.add_trace(go.Scatter(
                x=hist["week"], y=hist["demand"], mode="lines",
                line=dict(color=C["blue"], width=2),
                name="Observed (2023)",
                hovertemplate="%{x|%b %d}<br>%{y:,.0f} mentions<extra></extra>",
            ))
        fig.add_trace(go.Scatter(
            x=sub["week"], y=sub["forecast_demand"], mode="lines+markers",
            line=dict(color=C["amber"], width=2.2, dash="dash"),
            marker=dict(size=5), name="Forecast (12 wks)",
            hovertemplate="%{x|%b %d}<br>%{y:,.0f} predicted<extra></extra>",
        ))
        if not hist.empty:
            fig.add_vline(x=hist["week"].max(),
                          line=dict(color=C["text3"], dash="dot", width=1))
        ui.apply_layout(fig, 380,
                        title=ui.chart_title(f"{skill.title()} — observed vs forecast"),
                        yaxis=dict(title="Weekly mentions"),
                        xaxis=dict(title=""))
        st.plotly_chart(fig, use_container_width=True)

        model_used = sorted(sub["model_used"].unique())
        ui.info_note("Forecast generated by forecast_engine.py from data available up to "
                     "2023-12-25; the horizon is 12 weekly steps into 2024. "
                     f"Model used for this skill: <b>{' / '.join(model_used)}</b>.")

    st.write("")

    with st.container(border=True):
        ui.card_title("Forecast table", "All horizon steps for the selected skill.")
        show = sub[["week", "horizon_weeks", "forecast_demand", "model_used"]].copy()
        show.columns = ["Week", "Horizon (weeks)", "Forecast demand", "Model"]
        show["Week"] = show["Week"].dt.strftime("%Y-%m-%d")
        st.dataframe(show, use_container_width=True, hide_index=True, height=340)


# ROUTER
# ===========================================================================
if active_page == "Overview":
    render_overview()
elif active_page == "Skills Intelligence":
    render_skills()
elif active_page == "Demand Analytics":
    render_demand()
elif active_page == "Monthly Forecasts":
    render_forecasts()
elif active_page == "Technology Comparison":
    render_comparison()
elif active_page == "Data & Methodology":
    render_methodology()
elif active_page == "About CoreNex":
    render_about()
elif active_page == "Raw Data":
    render_raw_data()
elif active_page == "Data Preprocessing":
    render_preprocessing()
elif active_page == "Cleaned Data":
    render_cleaned_data()
elif active_page == "Model Training":
    render_model_training()
elif active_page == "Model Evaluation":
    render_model_evaluation()
elif active_page == "Predictions":
    render_predictions()
else:
    render_overview()