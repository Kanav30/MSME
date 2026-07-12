"""
MSME Financial Health Card — Console UI
----------------------------------------
A professional, bank-facing front end for the alternate-data scoring engine.

Two roles:
  - MSME self-assessment: fetch alternate data via a simulated Account Aggregator
    consent flow, view the multidimensional pillar breakdown, run what-if scenarios,
    and generate a credit health certificate.
  - Credit Officer console: prioritized lead queue and per-borrower deep-dive.

Design: institutional financial terminal. Slate base, single teal accent,
monospaced figures. No decorative emoji.
"""

import os

import pandas as pd
import streamlit as st

import scoring_core

st.set_page_config(
    page_title="MSME Financial Health Card",
    layout="wide",
    initial_sidebar_state="expanded",
)

RM_ACCESS_CODE = os.getenv("RM_DEMO_ACCESS_CODE", "idbi2026")

# ---------------------------------------------------------------------------
# Design system
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    :root {
        --ink:      #0d1b2a;
        --panel:    #16283c;
        --panel-2:  #1e3550;
        --line:     #2b4059;
        --teal:     #2dd4bf;
        --teal-dim: #14b8a6;
        --amber:    #f59e0b;
        --red:      #ef4444;
        --green:    #22c55e;
        --text:     #e8eef5;
        --muted:    #8aa0b8;
    }

    html, body, [class*="css"], .stApp {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    .stApp { background: var(--ink); color: var(--text); }

    .figure { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }

    /* Eyebrow labels */
    .eyebrow {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
        color: var(--muted); margin: 0 0 4px 0;
    }

    /* Panels */
    .panel {
        background: var(--panel); border: 1px solid var(--line);
        border-radius: 10px; padding: 22px;
    }

    /* Score hero */
    .score-hero {
        background: linear-gradient(135deg, var(--panel) 0%, var(--panel-2) 100%);
        border: 1px solid var(--line); border-left: 3px solid var(--teal);
        border-radius: 12px; padding: 26px 28px;
    }
    .score-value {
        font-family: 'IBM Plex Mono', monospace; font-weight: 600;
        font-size: 64px; line-height: 1; color: var(--text); margin: 6px 0;
    }
    .score-band {
        font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: var(--muted);
    }
    .pill {
        display: inline-block; font-family: 'IBM Plex Mono', monospace;
        font-size: 12px; font-weight: 500; padding: 4px 12px; border-radius: 20px;
        letter-spacing: 0.5px;
    }
    .pill-low   { background: rgba(34,197,94,0.14);  color: #4ade80; border: 1px solid rgba(34,197,94,0.35); }
    .pill-med   { background: rgba(245,158,11,0.14); color: #fbbf24; border: 1px solid rgba(245,158,11,0.35); }
    .pill-high  { background: rgba(239,68,68,0.14);  color: #f87171; border: 1px solid rgba(239,68,68,0.35); }

    /* Pillar rows */
    .pillar-row { margin: 14px 0; }
    .pillar-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
    .pillar-name { font-size: 14px; font-weight: 500; color: var(--text); }
    .pillar-score { font-family: 'IBM Plex Mono', monospace; font-size: 14px; color: var(--muted); }
    .pillar-track { height: 8px; background: var(--panel-2); border-radius: 6px; overflow: hidden; }
    .pillar-fill { height: 100%; border-radius: 6px; }

    /* Factor chips */
    .factor {
        display: flex; justify-content: space-between; gap: 12px;
        padding: 10px 14px; border-radius: 8px; margin: 6px 0;
        background: var(--panel-2); border: 1px solid var(--line);
    }
    .factor-name { font-size: 13px; color: var(--text); }
    .factor-detail { font-size: 12px; color: var(--muted); }
    .factor-pos { font-family: 'IBM Plex Mono', monospace; color: #4ade80; font-weight: 600; font-size: 13px; }
    .factor-neg { font-family: 'IBM Plex Mono', monospace; color: #f87171; font-weight: 600; font-size: 13px; }

    /* Certificate */
    .certificate {
        background: #fbfcfd; color: #16283c; border-radius: 12px;
        padding: 44px; border: 1px solid #d5dee8;
        box-shadow: 0 20px 48px rgba(0,0,0,0.35);
    }
    .cert-rule { border: none; border-top: 2px solid #16283c; margin: 18px 0; }

    /* Auth cards */
    .auth-card {
        background: var(--panel); border: 1px solid var(--line);
        border-radius: 12px; padding: 30px; height: 100%;
    }
    .auth-card h3 { margin-top: 0; }

    /* Step chips for AA flow */
    .step { font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--muted); }
    .step-done { color: var(--teal); }

    /* Streamlit chrome */
    section[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--line); }
    .stButton>button {
        font-family:'IBM Plex Sans',sans-serif; font-weight:500; border-radius:8px;
        border:1px solid var(--line);
    }
    div[data-testid="stMetricValue"] { font-family:'IBM Plex Mono',monospace; }
    h1,h2,h3,h4 { font-family:'IBM Plex Sans',sans-serif; letter-spacing:-0.01em; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session + helpers
# ---------------------------------------------------------------------------
for key, default in [("user_role", None), ("aa_status", "none"), ("aa_data", None), ("aa_handle", None)]:
    if key not in st.session_state:
        st.session_state[key] = default


def logout():
    for k in ("user_role", "aa_status", "aa_data", "aa_handle"):
        st.session_state[k] = None if k == "user_role" else ("none" if k == "aa_status" else None)


def call_scoring_api(payload: dict) -> dict | None:
    """Score a profile in-process. Named call_scoring_api for continuity, but it
    now calls the shared scoring core directly — no network hop, no separate
    backend to keep alive."""
    try:
        return scoring_core.score_profile(payload)
    except Exception as e:  # noqa: BLE001
        st.error(f"Scoring failed: {e}")
    return None


def risk_pill(tier: str) -> str:
    cls = "pill-low" if tier == "Low Risk" else "pill-med" if tier == "Medium Risk" else "pill-high"
    return f"<span class='pill {cls}'>{tier}</span>"


def pillar_color(score: float) -> str:
    if score >= 70:
        return "#22c55e"
    if score >= 45:
        return "#f59e0b"
    return "#ef4444"


def render_pillars(pillars: list[dict]):
    for p in pillars:
        col = pillar_color(p["score"])
        pct = max(2, min(100, p["score"]))
        st.markdown(
            f"""
            <div class='pillar-row'>
              <div class='pillar-head'>
                <span class='pillar-name'>{p['label']}
                    <span style='color:var(--muted); font-size:12px;'>· weight {int(p['weight']*100)}%</span>
                </span>
                <span class='pillar-score figure'>{p['score']:.0f}/100</span>
              </div>
              <div class='pillar-track'><div class='pillar-fill' style='width:{pct}%; background:{col};'></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_factors(explain: dict):
    st.markdown("<p class='eyebrow'>Top score drivers</p>", unsafe_allow_html=True)
    for item in explain["positive"][:3]:
        st.markdown(
            f"<div class='factor'><div><div class='factor-name'>{item['factor']}</div>"
            f"<div class='factor-detail'>{item.get('detail','')}</div></div>"
            f"<div class='factor-pos'>{item['impact']}</div></div>",
            unsafe_allow_html=True,
        )
    st.markdown("<p class='eyebrow' style='margin-top:16px;'>Top score detractors</p>", unsafe_allow_html=True)
    if not explain["negative"]:
        st.markdown("<div class='factor'><div class='factor-name'>No material detractors identified.</div></div>",
                    unsafe_allow_html=True)
    for item in explain["negative"][:3]:
        st.markdown(
            f"<div class='factor'><div><div class='factor-name'>{item['factor']}</div>"
            f"<div class='factor-detail'>{item.get('detail','')}</div></div>"
            f"<div class='factor-neg'>{item['impact']}</div></div>",
            unsafe_allow_html=True,
        )


# ===========================================================================
# LOGIN
# ===========================================================================
if st.session_state.user_role is None:
    st.markdown("<p class='eyebrow' style='text-align:center;'>Alternate-Data Credit Infrastructure</p>",
                unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center; margin-top:0;'>MSME Financial Health Card</h1>",
                unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; color:var(--muted); max-width:640px; margin:0 auto 30px;'>"
        "A multidimensional health score for New-to-Credit and New-to-Bank enterprises, "
        "built on GST, UPI, Account Aggregator and EPFO signals — not financial statements.</p>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
        st.markdown("<p class='eyebrow'>Borrower access</p>", unsafe_allow_html=True)
        st.markdown("### MSME Self-Assessment")
        st.write("Fetch your alternate data through a consent-based pull, view your "
                 "five-pillar health score, run what-if scenarios, and generate a health certificate.")
        if st.button("Enter as MSME", use_container_width=True, type="primary"):
            st.session_state.user_role = "msme"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
        st.markdown("<p class='eyebrow'>Lender access</p>", unsafe_allow_html=True)
        st.markdown("### Credit Officer Console")
        st.write("Review a prioritized lead queue and drill into per-borrower assessments "
                 "with pillar-level explainability.")
        code = st.text_input("Access code", type="password", help="Demo credential: idbi2026")
        if st.button("Sign in", use_container_width=True):
            if code == RM_ACCESS_CODE:
                st.session_state.user_role = "rm"
                st.rerun()
            else:
                st.error("Incorrect access code.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        "<p style='text-align:center; color:var(--muted); font-size:12px; margin-top:34px;'>"
        "Demo build. Data sources are simulated via an Account Aggregator / OCEN mock layer. "
        "Outputs are not credit decisions.</p>",
        unsafe_allow_html=True,
    )

# ===========================================================================
# MSME SELF-ASSESSMENT
# ===========================================================================
elif st.session_state.user_role == "msme":
    st.sidebar.button("Log out", on_click=logout, use_container_width=True)
    st.sidebar.markdown("<p class='eyebrow'>Applicant</p>", unsafe_allow_html=True)
    client_name = st.sidebar.text_input("Business name", value="Balaji Textile Processing Mills")

    # --- Simulated Account Aggregator consent flow ---------------------------
    st.sidebar.markdown("<p class='eyebrow' style='margin-top:18px;'>Data source</p>", unsafe_allow_html=True)
    if st.session_state.aa_status != "fetched":
        st.sidebar.caption("Pull alternate data through a consent-based Account Aggregator flow.")
        if st.sidebar.button("Fetch via Account Aggregator", use_container_width=True, type="primary"):
            try:
                fetched = scoring_core.aa_consent_and_fetch(client_name)
                st.session_state.aa_handle = fetched["consent_handle"]
                st.session_state.aa_data = fetched["data"]
                st.session_state.aa_status = "fetched"
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"AA fetch failed: {e}")
        st.sidebar.caption("Or enter figures manually below.")
    else:
        st.sidebar.success(f"Data received · consent {st.session_state.aa_handle}")
        if st.sidebar.button("Reset consent", use_container_width=True):
            st.session_state.aa_status = "none"
            st.session_state.aa_data = None
            st.rerun()

    src = st.session_state.aa_data or {}

    st.sidebar.markdown("<p class='eyebrow' style='margin-top:18px;'>Alternate-data inputs</p>", unsafe_allow_html=True)
    gst_revenue = st.sidebar.number_input("Avg monthly GST turnover (Rs)",
                                          value=int(src.get("gst_avg_monthly_revenue", 1450000)), step=50000, min_value=0)
    gst_delay = st.sidebar.number_input("Avg GST filing delay (days)",
                                        value=int(src.get("gst_filing_delay_days", 3)), step=1, min_value=0)
    upi_volume = st.sidebar.number_input("Monthly UPI transactions",
                                         value=int(src.get("upi_monthly_txns", 890)), step=5, min_value=0)
    upi_value = st.sidebar.number_input("Average UPI ticket size (Rs)",
                                        value=float(src.get("upi_avg_txn_value", 1450.0)), step=50.0, min_value=0.0)
    bank_float = st.sidebar.number_input("Avg bank balance (Rs)",
                                         value=float(src.get("aa_avg_bank_balance", 380000.0)), step=10000.0, min_value=0.0)
    staff_count = st.sidebar.number_input("EPFO active headcount",
                                          value=int(src.get("epfo_employee_count", 18)), step=1, min_value=0)
    vintage = st.sidebar.number_input("Business vintage (years)",
                                      value=int(src.get("business_vintage_years", 4)), step=1, min_value=0)

    st.sidebar.markdown("<p class='eyebrow' style='margin-top:18px;'>What-if scenario</p>", unsafe_allow_html=True)
    sim_gst_shift = st.sidebar.slider("Projected revenue change (%)", -50, 50, 0, step=5)
    sim_bounce_count = st.sidebar.slider("Projected bounced payments (6m)", 0, 10, int(src.get("aa_bounced_txns_6m", 1)), step=1)
    sim_inventory_shift = st.sidebar.slider("Projected inventory/capex growth (%)", -10, 50,
                                            int(src.get("inventory_growth_trend", 15)), step=5)

    processed_gst = gst_revenue * (1 + sim_gst_shift / 100)
    payload_body = {
        "gst_avg_monthly_revenue": float(processed_gst),
        "gst_filing_delay_days": int(gst_delay),
        "upi_monthly_txns": int(upi_volume),
        "upi_avg_txn_value": float(upi_value),
        "aa_avg_bank_balance": float(bank_float),
        "aa_bounced_txns_6m": int(sim_bounce_count),
        "epfo_employee_count": int(staff_count),
        "business_vintage_years": int(vintage),
        "inventory_growth_trend": float(sim_inventory_shift),
    }

    st.markdown("<p class='eyebrow'>Financial Health Card</p>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='margin-top:0;'>{client_name}</h2>", unsafe_allow_html=True)

    res = call_scoring_api(payload_body)
    if res is None:
        st.stop()
    need = res["business_need"]

    tab_dash, tab_cert = st.tabs(["Health assessment", "Certificate"])

    with tab_dash:
        left, right = st.columns([1.1, 1], gap="large")

        with left:
            tier = res["risk_assessment"]
            st.markdown(
                f"""
                <div class='score-hero'>
                    <p class='eyebrow'>Financial Health Score</p>
                    <div class='score-value'>{res['financial_health_score']}<span style='font-size:22px; color:var(--muted);'> / 900</span></div>
                    <div style='display:flex; gap:14px; align-items:center; margin-top:8px;'>
                        {risk_pill(tier)}
                        <span class='score-band'>Grade {res['health_grade']} · Composite {res['composite_100']:.0f}/100</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            st.markdown("<p class='eyebrow'>Multidimensional breakdown</p>", unsafe_allow_html=True)
            render_pillars(res["pillars"])

            mlc = res.get("ml_cross_check")
            if mlc:
                st.markdown(
                    f"<div class='factor' style='margin-top:14px;'>"
                    f"<div><div class='factor-name'>{mlc['label']}</div>"
                    f"<div class='factor-detail'>{mlc['note']}</div></div>"
                    f"<div class='pillar-score figure'>{mlc['ml_score']}</div></div>",
                    unsafe_allow_html=True,
                )

        with right:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            st.markdown("<p class='eyebrow'>Assessment summary</p>", unsafe_allow_html=True)
            st.write(res["ai_insight"])
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            st.markdown(
                f"<p class='eyebrow'>Matched credit product</p>"
                f"<div style='font-size:18px; font-weight:600; margin-bottom:2px;'>{need['product']}</div>"
                f"<div class='factor-detail'>{need['need']} · confidence {need['confidence']} · "
                f"opportunity {res['opportunity_score']}%</div>",
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            render_factors(res["explainability"])
            st.markdown("</div>", unsafe_allow_html=True)

    with tab_cert:
        st.caption("Use your browser print dialog (Ctrl/Cmd + P) to export this certificate as PDF.")
        st.markdown(
            f"""
            <div class='certificate'>
                <div style='text-align:center;'>
                    <p style='font-family:IBM Plex Mono,monospace; letter-spacing:3px; font-size:12px; color:#5b7089; margin:0;'>ALTERNATE-DATA CREDIT ASSESSMENT</p>
                    <h1 style='margin:6px 0 0; letter-spacing:1px; color:#16283c;'>MSME FINANCIAL HEALTH CARD</h1>
                </div>
                <hr class='cert-rule'/>
                <table style='width:100%; font-size:15px; line-height:2.1;'>
                    <tr><td style='color:#5b7089; width:42%;'>Business</td><td style='font-weight:600;'>{client_name}</td></tr>
                    <tr><td style='color:#5b7089;'>Financial Health Score</td><td style='font-family:IBM Plex Mono,monospace; font-weight:600;'>{res['financial_health_score']} / 900</td></tr>
                    <tr><td style='color:#5b7089;'>Credit Grade</td><td style='font-family:IBM Plex Mono,monospace; font-weight:600;'>{res['health_grade']}</td></tr>
                    <tr><td style='color:#5b7089;'>Risk Tier</td><td style='font-weight:600;'>{res['risk_assessment']}</td></tr>
                    <tr><td style='color:#5b7089;'>Composite (0-100)</td><td style='font-family:IBM Plex Mono,monospace; font-weight:600;'>{res['composite_100']:.0f}</td></tr>
                </table>
                <div style='background:#eef3f8; border-left:4px solid #14b8a6; padding:16px 18px; border-radius:6px; margin-top:14px;'>
                    <p style='margin:0 0 2px; font-size:12px; color:#5b7089; letter-spacing:1px;'>SUGGESTED CREDIT PRODUCT</p>
                    <p style='margin:0; font-size:16px; font-weight:600; color:#16283c;'>{need['product']}</p>
                </div>
                <p style='font-size:11px; color:#8598ac; text-align:center; margin-top:28px;'>
                    Derived from GST, UPI, Account Aggregator and EPFO alternate-data signals via a transparent
                    five-pillar scorecard. Demo output — not a credit decision.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ===========================================================================
# CREDIT OFFICER CONSOLE
# ===========================================================================
elif st.session_state.user_role == "rm":
    st.sidebar.button("Sign out", on_click=logout, use_container_width=True)
    st.markdown("<p class='eyebrow'>Lender view</p>", unsafe_allow_html=True)
    st.markdown("<h2 style='margin-top:0;'>Credit Officer Console</h2>", unsafe_allow_html=True)

    view = st.radio("View", ["Priority queue", "Borrower deep-dive"], horizontal=True, label_visibility="collapsed")
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    rm_db = {
        "Radhe Krishna Textile Mills": {
            "gst_avg_monthly_revenue": 1950000.0, "gst_filing_delay_days": 1, "upi_monthly_txns": 1120,
            "upi_avg_txn_value": 2100.0, "aa_avg_bank_balance": 210000.0, "aa_bounced_txns_6m": 0,
            "epfo_employee_count": 16, "business_vintage_years": 4, "inventory_growth_trend": 18.0,
        },
        "Balaji Auto Components Co": {
            "gst_avg_monthly_revenue": 3400000.0, "gst_filing_delay_days": 5, "upi_monthly_txns": 410,
            "upi_avg_txn_value": 4500.0, "aa_avg_bank_balance": 1200000.0, "aa_bounced_txns_6m": 1,
            "epfo_employee_count": 22, "business_vintage_years": 7, "inventory_growth_trend": 5.0,
        },
        "Sunrise Tech Logistics Group": {
            "gst_avg_monthly_revenue": 640000.0, "gst_filing_delay_days": 22, "upi_monthly_txns": 120,
            "upi_avg_txn_value": 900.0, "aa_avg_bank_balance": 45000.0, "aa_bounced_txns_6m": 4,
            "epfo_employee_count": 5, "business_vintage_years": 2, "inventory_growth_trend": -6.0,
        },
    }

    if view == "Priority queue":
        st.markdown("<p class='eyebrow'>Accounts with strong alternate-data signals and no existing credit line</p>",
                    unsafe_allow_html=True)
        rows = []
        for name, prof in rm_db.items():
            r = call_scoring_api(prof)
            if r is None:
                st.stop()
            action = ("Immediate outreach" if r["financial_health_score"] >= 700
                      else "Monitor" if r["financial_health_score"] >= 520
                      else "Manual review")
            rows.append({
                "Borrower": name,
                "Health score": r["financial_health_score"],
                "Grade": r["health_grade"],
                "Risk tier": r["risk_assessment"],
                "Matched product": r["business_need"]["product"],
                "Recommended action": action,
            })
        df = pd.DataFrame(rows).sort_values("Health score", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)

    else:
        chosen = st.selectbox("Account", list(rm_db.keys()))
        r = call_scoring_api(rm_db[chosen])
        if r is None:
            st.stop()

        st.markdown(f"<h3 style='margin-bottom:2px;'>{chosen}</h3>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-bottom:14px;'>{risk_pill(r['risk_assessment'])}</div>", unsafe_allow_html=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Health score", f"{r['financial_health_score']} / 900", r["health_grade"])
        m2.metric("Composite", f"{r['composite_100']:.0f} / 100")
        m3.metric("Opportunity", f"{r['opportunity_score']}%")

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        left, right = st.columns([1.1, 1], gap="large")
        with left:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            st.markdown("<p class='eyebrow'>Pillar breakdown</p>", unsafe_allow_html=True)
            render_pillars(r["pillars"])
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            st.markdown("<p class='eyebrow'>Assessment</p>", unsafe_allow_html=True)
            st.write(r["ai_insight"])
            st.markdown(
                f"<p class='eyebrow' style='margin-top:10px;'>Recommended action</p>"
                f"<div style='font-size:15px; font-weight:600;'>{r['business_need']['product']}</div>"
                f"<div class='factor-detail'>{r['business_need']['need']} · confidence {r['business_need']['confidence']}</div>",
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            render_factors(r["explainability"])
            st.markdown("</div>", unsafe_allow_html=True)
