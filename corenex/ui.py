"""
CoreNex -- Shared design system & UI components
================================================

Premium LIGHT enterprise SaaS theme (Phase 3 redesign).

Design tokens: white surfaces, soft off-white canvas (#F7F9FC), primary blue
(#2563EB), secondary teal (#0891B2), navy typography (#172033), hairline
borders (#E5EAF1), soft shadows and consistent 12px radii.

Nothing here contains data logic -- presentation only.
"""

from __future__ import annotations

import streamlit as st

# --------------------------------------------------------------------------
# Palette (single source of truth)
# --------------------------------------------------------------------------
C = dict(
    # surfaces
    bg="#F7F9FC",          # app canvas
    sidebar="#FFFFFF",     # navigation rail
    panel="#FFFFFF",       # cards / panels
    card="#FFFFFF",
    card_alt="#F8FAFC",    # subtle inner surfaces
    # lines
    border="#E5EAF1",
    border_hi="#D3DCE8",
    grid="#EEF2F7",
    # brand
    blue="#2563EB",
    blue_dark="#1D4ED8",
    blue_soft="#EFF4FF",
    cyan="#0891B2",
    teal_soft="#ECFEFF",
    violet="#7C3AED",
    green="#059669",
    amber="#D97706",
    red="#DC2626",
    pink="#DB2777",
    # typography
    text="#172033",
    text2="#5A6B85",
    text3="#8A97AB",
)

# Ordered categorical palette for charts (blue -> teal -> violet -> amber ...).
CHART_COLORS = [
    "#2563EB", "#0891B2", "#7C3AED", "#D97706",
    "#059669", "#DB2777", "#4F46E5", "#0EA5E9",
]

STATUS_COLORS = {
    "Validated":        C["green"],
    "Provisional":      C["amber"],
    "Experimental":     C["violet"],
    "Insufficient data": C["red"],
}

MODEL_COLORS = {
    "Naive":          "#94A3B8",
    "SeasonalNaive":  "#64748B",
    "MovingAverage3": "#7C3AED",
    "LinearTrend":    "#0891B2",
    "HoltLinear":     "#2563EB",
    "DampedHolt":     "#059669",
    "XGBoost":        "#DB2777",
}

SHADOW_SM = "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)"
SHADOW_MD = "0 1px 2px rgba(16,24,40,0.04), 0 6px 18px rgba(16,24,40,0.06)"

RADIUS = "12px"


# --------------------------------------------------------------------------
# Global CSS
# --------------------------------------------------------------------------
def inject_css() -> None:
    """Global theme + component CSS (premium light enterprise look)."""
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
  color: {C['text']};
}}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
  background: {C['bg']} !important;
}}
.block-container {{
  background: transparent !important;
  padding: 1.6rem 2.2rem 4rem !important;
  max-width: 1560px !important;
}}
[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
[data-testid="stDecoration"] {{ display: none !important; }}

/* ---------------- Sidebar ---------------- */
section[data-testid="stSidebar"] {{
  background: {C['sidebar']} !important;
  border-right: 1px solid {C['border']} !important;
  min-width: 264px !important;
  max-width: 264px !important;
}}
[data-testid="stSidebarContent"] {{ padding: 20px 12px 12px !important; }}
[data-testid="stSidebarCollapsedControl"] {{ color: {C['text2']} !important; }}

section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: 2px !important; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label {{
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  padding: 9px 12px !important;
  margin: 1px 0 !important;
  border-radius: 8px !important;
  color: {C['text2']} !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  line-height: 1.25 !important;
  cursor: pointer !important;
  transition: background .12s ease, color .12s ease;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
  background: #F2F6FC !important;
  color: {C['text']} !important;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
  background: {C['blue_soft']} !important;
  color: {C['blue']} !important;
  font-weight: 600 !important;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {{
  flex-shrink: 0 !important;
  width: 15px !important;
  height: 15px !important;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child > div {{
  border-color: {C['border_hi']} !important;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) > div:first-child > div {{
  border-color: {C['blue']} !important;
  background: {C['blue']} !important;
}}
section[data-testid="stSidebar"] .st-key-nav_analytics div[role="radiogroup"] label::before,
section[data-testid="stSidebar"] .st-key-nav_ml div[role="radiogroup"] label::before {{
  font-size: 12.5px;
  width: 15px;
  text-align: center;
  opacity: .95;
}}
/* Analytics group */
.st-key-nav_analytics div[role="radiogroup"] label:nth-of-type(1)::before {{ content: "▦"; }}
.st-key-nav_analytics div[role="radiogroup"] label:nth-of-type(2)::before {{ content: "◈"; }}
.st-key-nav_analytics div[role="radiogroup"] label:nth-of-type(3)::before {{ content: "◭"; }}
.st-key-nav_analytics div[role="radiogroup"] label:nth-of-type(4)::before {{ content: "◯"; }}
.st-key-nav_analytics div[role="radiogroup"] label:nth-of-type(5)::before {{ content: "◇"; }}
.st-key-nav_analytics div[role="radiogroup"] label:nth-of-type(6)::before {{ content: "▤"; }}
.st-key-nav_analytics div[role="radiogroup"] label:nth-of-type(7)::before {{ content: "◉"; }}
/* ML workflow group */
.st-key-nav_ml div[role="radiogroup"] label:nth-of-type(1)::before {{ content: "▷"; }}
.st-key-nav_ml div[role="radiogroup"] label:nth-of-type(2)::before {{ content: "⚙"; }}
.st-key-nav_ml div[role="radiogroup"] label:nth-of-type(3)::before {{ content: "▦"; }}
.st-key-nav_ml div[role="radiogroup"] label:nth-of-type(4)::before {{ content: "◈"; }}
.st-key-nav_ml div[role="radiogroup"] label:nth-of-type(5)::before {{ content: "◔"; }}
.st-key-nav_ml div[role="radiogroup"] label:nth-of-type(6)::before {{ content: "◎"; }}

/* ---------------- Form controls ---------------- */
[data-testid="stWidgetLabel"] p, .stSelectbox label p, .stMultiSelect label p,
.stRadio label p, .stSlider label p {{
  font-size: 10.5px !important;
  text-transform: uppercase !important;
  letter-spacing: .7px !important;
  color: {C['text3']} !important;
  font-weight: 600 !important;
}}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {{
  background: {C['panel']} !important;
  border: 1px solid {C['border']} !important;
  border-radius: 8px !important;
  color: {C['text']} !important;
  font-size: 13px !important;
  box-shadow: none !important;
}}
[data-testid="stTextInput"] input:focus {{ border-color: {C['blue']} !important;
  box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important; }}

div[data-baseweb="select"] > div, [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {{
  background: {C['panel']} !important;
  border: 1px solid {C['border']} !important;
  border-radius: 8px !important;
  min-height: 38px !important;
  box-shadow: none !important;
}}
div[data-baseweb="select"] [data-testid="stMarkdownContainer"] p {{ color: {C['text']} !important;
  font-size: 13px !important; }}
[data-baseweb="popover"] {{ border-radius: 10px !important; }}
[data-baseweb="menu"] {{ background: {C['panel']} !important; }}

[data-testid="stSlider"] div[role="slider"] {{ background: {C['blue']} !important; }}
[data-testid="stSlider"] div[role="slider"]:focus {{ box-shadow: 0 0 0 4px rgba(37,99,235,0.15) !important; }}
[data-testid="stSlider"] [data-testid="stTickBar"] > div, .stSlider [data-baseweb="slider"] div {{
  background: {C['blue']} !important;
}}

div[data-baseweb="tab-list"] {{
  background: {C['card_alt']} !important;
  border: 1px solid {C['border']} !important;
  border-radius: 10px !important;
  padding: 3px !important;
  gap: 2px !important;
  width: fit-content !important;
}}
button[data-baseweb="tab"] {{
  background: transparent !important;
  color: {C['text2']} !important;
  border-radius: 7px !important;
  font-size: 12.5px !important;
  font-weight: 500 !important;
  padding: 7px 18px !important;
  border: none !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
  background: {C['panel']} !important;
  color: {C['blue']} !important;
  font-weight: 600 !important;
  box-shadow: {SHADOW_SM};
}}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {{ display: none !important; }}

/* ---------------- Cards / containers ---------------- */
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: {C['panel']} !important;
  border: 1px solid {C['border']} !important;
  border-radius: {RADIUS} !important;
  box-shadow: {SHADOW_MD};
  padding: 0 !important;
}}
[data-testid="stVerticalBlockBorderWrapper"] > div {{
  padding: 18px 20px 16px !important;
}}
[data-testid="stVerticalBlockBorderWrapper"]:has(div[role="radiogroup"]) {{
  box-shadow: none !important;
  border: none !important;
  background: transparent !important;
}}

[data-testid="stExpander"] {{
  background: {C['panel']} !important;
  border: 1px solid {C['border']} !important;
  border-radius: 10px !important;
  box-shadow: {SHADOW_SM};
}}
[data-testid="stExpander"] summary {{ color: {C['text']} !important; font-size: 13px !important;
  font-weight: 600 !important; }}
[data-testid="stExpander"] details > div {{ color: {C['text2']} !important; }}

/* ---------------- Data display ---------------- */
[data-testid="stDataFrameResizable"], [data-testid="stDataFrame"] {{
  border: 1px solid {C['border']} !important;
  border-radius: 10px !important;
  overflow: hidden;
  background: {C['panel']} !important;
}}
[data-testid="stDataFrame"] [role="row"]:first-child, .stDataFrame thead tr {{
  background: {C['card_alt']} !important;
}}
[data-testid="stDataFrame"] th, .stDataFrame th {{
  color: {C['text2']} !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: .5px;
}}
[data-testid="stDataFrame"] td, .stDataFrame td {{ color: {C['text']} !important; font-size: 12.5px !important; }}

/* ---------------- Alerts ---------------- */
[data-testid="stAlert"] {{
  background: {C['blue_soft']} !important;
  border: 1px solid #D6E2FF !important;
  border-radius: 10px !important;
}}
[data-testid="stAlert"] p, [data-testid="stAlert"] div {{ color: {C['text2']} !important; }}

hr {{ border-color: {C['border']} !important; margin: 10px 0 16px !important; }}

p, li, label {{ color: {C['text2']}; font-size: 13px; line-height: 1.6; }}
a {{ color: {C['blue']} !important; }}
code {{ background: {C['card_alt']} !important; color: {C['text']} !important;
  border: 1px solid {C['border']} !important; border-radius: 5px !important;
  padding: 1px 5px !important; font-size: 11.5px !important; }}

/* ---------------- CoreNex primitives ---------------- */
.cn-page-title {{
  font-size: 22px !important; font-weight: 700 !important; color: {C['text']} !important;
  letter-spacing: -.6px !important; margin: 0 0 3px !important;
}}
.cn-page-sub {{
  font-size: 13px !important; color: {C['text2']} !important; margin: 0 0 6px !important;
  max-width: 980px; line-height: 1.55;
}}
.cn-section-label {{
  font-size: 10px; text-transform: uppercase; letter-spacing: .9px; color: {C['text3']};
  font-weight: 700; margin-bottom: 9px;
}}
.cn-card-title {{
  font-size: 13.5px; font-weight: 650; color: {C['text']}; letter-spacing: -.1px;
  margin: 0 0 2px;
}}
.cn-card-sub {{ font-size: 11.5px; color: {C['text3']}; margin: 0 0 12px; line-height: 1.5; }}

.cn-panel {{
  background: {C['panel']}; border: 1px solid {C['border']}; border-radius: {RADIUS};
  padding: 18px 20px; box-shadow: {SHADOW_SM};
}}
.cn-note {{ font-size: 12px; color: {C['text2']}; line-height: 1.62; }}
.cn-note strong, .cn-note b {{ color: {C['text']}; font-weight: 600; }}

.cn-kpi {{
  background: {C['panel']}; border: 1px solid {C['border']}; border-radius: {RADIUS};
  padding: 16px 18px 15px; box-shadow: {SHADOW_MD}; height: 100%;
  position: relative; overflow: hidden;
}}
.cn-kpi-accent {{ position: absolute; left: 0; top: 0; bottom: 0; width: 3px; }}
.cn-kpi-label {{
  font-size: 10px; text-transform: uppercase; letter-spacing: .8px; color: {C['text3']};
  font-weight: 700; margin-bottom: 8px;
}}
.cn-kpi-value {{
  font-size: 26px; font-weight: 700; color: {C['text']}; letter-spacing: -.8px;
  font-variant-numeric: tabular-nums; line-height: 1.1;
}}
.cn-kpi-sub {{ font-size: 11.5px; font-weight: 600; margin-top: 6px; }}

.cn-badge {{
  display: inline-block; padding: 3px 9px; border-radius: 6px; font-size: 10.5px;
  font-weight: 700; letter-spacing: .3px;
}}
.cn-note-block {{ background: {C['card_alt']}; border: 1px solid {C['border']};
  border-radius: 10px; padding: 13px 15px; }}

.cn-split {{ display: flex; align-items: baseline; justify-content: space-between;
  gap: 12px; padding: 7px 0; border-bottom: 1px dashed {C['border']}; }}
.cn-split:last-child {{ border-bottom: none; }}
.cn-split-k {{ font-size: 12px; color: {C['text2']}; }}
.cn-split-v {{ font-size: 12.5px; font-weight: 650; color: {C['text']};
  font-variant-numeric: tabular-nums; }}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Layout primitives
# --------------------------------------------------------------------------
def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="cn-page-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="cn-page-sub">{subtitle}</div>', unsafe_allow_html=True)
    st.markdown(f'<hr style="margin:6px 0 18px;border-color:{C["border"]}">',
                unsafe_allow_html=True)


def section_label(text: str) -> None:
    st.markdown(f'<div class="cn-section-label">{text}</div>', unsafe_allow_html=True)


def card_title(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="cn-card-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="cn-card-sub">{subtitle}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", sub_color: str = "", accent: str = "") -> str:
    bar = (f'<div class="cn-kpi-accent" style="background:{accent}"></div>' if accent else "")
    sub_html = (f'<div class="cn-kpi-sub" style="color:{sub_color or C["text3"]}">{sub}</div>'
                if sub else "")
    return (f'<div class="cn-kpi">{bar}<div class="cn-kpi-label">{label}</div>'
            f'<div class="cn-kpi-value">{value}</div>{sub_html}</div>')


def kpi_row(items: list[dict], columns: int | None = None) -> None:
    """Render a responsive row of KPI cards."""
    cols = columns or len(items)
    st.markdown(f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:14px">'
                + "".join(kpi(**it) for it in items) + "</div>", unsafe_allow_html=True)


def badge(text: str, color: str) -> str:
    return (f'<span class="cn-badge" style="background:{color}14;color:{color};'
            f'border:1px solid {color}33">{text}</span>')


def status_badge(status: str) -> str:
    return badge(status, STATUS_COLORS.get(status, C["text2"]))


def split_rows(rows: list[tuple[str, str]], value_colors: dict | None = None) -> str:
    """Key/value definition rows for panels."""
    colors = value_colors or {}
    out = []
    for k, v in rows:
        col = colors.get(k, C["text"])
        out.append(f'<div class="cn-split"><span class="cn-split-k">{k}</span>'
                   f'<span class="cn-split-v" style="color:{col}">{v}</span></div>')
    return "".join(out)


def info_note(text: str) -> None:
    st.markdown(f'<div class="cn-note" style="margin-top:8px">{text}</div>', unsafe_allow_html=True)


def note_block(text: str) -> None:
    st.markdown(f'<div class="cn-note-block"><div class="cn-note">{text}</div></div>',
                unsafe_allow_html=True)


def empty_state(message: str, hint: str = "") -> None:
    st.markdown(f"""
<div class="cn-panel" style="text-align:center;padding:38px 20px">
  <div style="font-size:14px;font-weight:600;color:{C['text']};margin-bottom:6px">{message}</div>
  {f'<div class="cn-note">{hint}</div>' if hint else ''}
</div>""", unsafe_allow_html=True)


def error_state(message: str, hint: str = "") -> None:
    st.markdown(f"""
<div class="cn-panel" style="border-color:{C['red']}44;background:#FEF3F2;text-align:center;padding:32px 20px">
  <div style="font-size:14px;font-weight:600;color:{C['red']};margin-bottom:6px">{message}</div>
  {f'<div class="cn-note">{hint}</div>' if hint else ''}
</div>""", unsafe_allow_html=True)


def loading_spinner(text: str = "Loading data..."):
    return st.spinner(text)


# --------------------------------------------------------------------------
# Plotly theme (light)
# --------------------------------------------------------------------------
def chart_title(text: str) -> dict:
    return dict(text=text, font=dict(size=12.5, color=C["text"]), x=0, xanchor="left")


def apply_layout(fig, height: int = 340, **extra) -> None:
    """Apply the standard light layout to a figure, merging axis extras safely."""
    fig.update_layout(**plotly_layout(height, **extra))


def plotly_layout(height: int = 340, **extra) -> dict:
    """Standard light Plotly layout. Merge-safe: extra may include 'xaxis'/'yaxis'
    dicts, which are merged into the defaults rather than overwriting them."""
    base = dict(
        template="plotly_white",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=58, r=24, t=54, b=52),
        font=dict(family="Inter, -apple-system, Segoe UI, sans-serif",
                  color=C["text2"], size=11.5),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=C["border"],
                        font=dict(family="Inter", size=11.5, color=C["text"])),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11.5, color=C["text2"]),
                    orientation="h", y=1.06, x=0, xanchor="left", yanchor="bottom"),
        colorway=CHART_COLORS,
        title=dict(font=dict(size=12.5, color=C["text"]), x=0, xanchor="left"),
        xaxis=dict(gridcolor=C["grid"], showgrid=False,
                   tickfont=dict(color=C["text3"], size=10.5),
                   linecolor=C["border"], zeroline=False, ticks=""),
        yaxis=dict(gridcolor=C["grid"], showgrid=True,
                   tickfont=dict(color=C["text3"], size=10.5),
                   linecolor="rgba(0,0,0,0)", zeroline=False, ticks=""),
    )
    for k, v in extra.items():
        if k in ("xaxis", "yaxis") and isinstance(v, dict):
            merged = dict(base.get(k, {}))
            merged.update(v)
            base[k] = merged
        else:
            base[k] = v
    return base


def model_color(name: str) -> str:
    return MODEL_COLORS.get(name, C["blue"])


def trend_color(val: float, threshold: float = 5.0) -> str:
    if val is None or np_isnan(val):
        return C["text2"]
    if val > threshold:
        return C["green"]
    if val < -threshold:
        return C["red"]
    return C["text2"]


def np_isnan(v) -> bool:
    try:
        return v != v  # NaN is the only value not equal to itself
    except Exception:  # noqa: BLE001
        return False