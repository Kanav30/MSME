"""
Shared scoring core for the MSME Financial Health Card.

This module assembles the full scoring response (score, grade, risk tier,
pillars, explainability, product match, opportunity score, ML cross-check).
Both the FastAPI service (main.py) and the self-contained Streamlit app (app.py)
call these functions, so the deployed UI needs no separate backend.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from scorecard import compute_scorecard

# ---------------------------------------------------------------------------
# Optional ML cross-check model (secondary signal only)
# ---------------------------------------------------------------------------
# The pickled RandomForest was trained on scikit-learn 1.6.1 with a specific
# numpy build. Unpickling it against a different numpy can crash the process at
# the native level (a segfault Python can't catch) rather than raising cleanly.
# Since the ML model is only a secondary cross-check — the transparent scorecard
# is the decision score — we DON'T load it unless explicitly enabled via
# ENABLE_ML_CROSSCHECK=1. This keeps the hosted app crash-proof; the API
# (main.py) can still enable it in a matched local environment.
_ml_model = None
_ML_FEATURES: list[str] = []

if os.getenv("ENABLE_ML_CROSSCHECK", "0") == "1":
    try:
        import joblib

        _MODEL_PATH = os.getenv("MODEL_PATH", "msme_health_model.pkl")
        _ml_model = joblib.load(_MODEL_PATH)
        _ML_FEATURES = list(getattr(_ml_model, "feature_names_in_", []))
    except Exception:  # noqa: BLE001 - model is optional; degrade silently
        _ml_model = None
        _ML_FEATURES = []


def ml_is_loaded() -> bool:
    return _ml_model is not None


def ml_features() -> list[str]:
    return list(_ML_FEATURES)


def predict_business_need(data: dict, health_score: int) -> dict:
    """Map the applicant's profile to the most relevant credit product."""
    if data.get("inventory_growth_trend", 0) > 12 and health_score > 600:
        return {"need": "Inventory & asset scaling", "confidence": "94%", "product": "Smart Trade Inventory Line"}
    if data.get("upi_monthly_txns", 0) > 600 and data.get("aa_avg_bank_balance", 0) < 400_000:
        return {"need": "Working-capital cash-flow gap", "confidence": "89%", "product": "Express Cash-Flow Overdraft"}
    if health_score < 500:
        return {"need": "Pre-credit strengthening", "confidence": "71%", "product": "Guided Readiness Programme"}
    return {"need": "General capital expenditure", "confidence": "76%", "product": "Corporate Growth Credit Line"}


def ml_cross_check(data: dict) -> dict | None:
    """Run the secondary ML model, if available, purely as a comparison signal."""
    if _ml_model is None or not _ML_FEATURES:
        return None
    try:
        import pandas as pd

        row = {f: data[f] for f in _ML_FEATURES if f in data}
        pred = float(_ml_model.predict(pd.DataFrame([row]))[0])
        pred = int(max(300, min(900, pred)))
        return {
            "ml_score": pred,
            "label": "Experimental ML cross-check (RandomForest)",
            "note": "Secondary signal only. The scorecard above is the decision score.",
        }
    except Exception:  # noqa: BLE001
        return None


def build_ai_insight(data: dict, result: dict) -> str:
    lines = []
    weakest = min(result["pillars"], key=lambda p: p["score"])
    strongest = max(result["pillars"], key=lambda p: p["score"])
    lines.append(f"Strongest pillar is {strongest['label']} ({strongest['score']:.0f}/100).")
    lines.append(f"Weakest is {weakest['label']} ({weakest['score']:.0f}/100) — the primary lever to improve.")
    if data.get("aa_bounced_txns_6m", 0) > 0:
        lines.append(f"{data['aa_bounced_txns_6m']} bounced transaction(s) are dragging Banking Discipline.")
    else:
        lines.append("Clean dishonour record supports the risk tier.")
    return " ".join(lines)


def score_profile(data: dict) -> dict:
    """Full assessment for a single MSME profile. This is the single source of truth."""
    result = compute_scorecard(data)
    health_score = result["financial_health_score"]

    base_opportunity = 45
    opp_inventory = max(0, data.get("inventory_growth_trend", 0) * 1.4)
    opp_velocity = min(
        25,
        ((data.get("upi_monthly_txns", 0) * data.get("upi_avg_txn_value", 0))
         / max(1, data.get("aa_avg_bank_balance", 1))) * 4,
    )
    opp_scale = min(15, data.get("epfo_employee_count", 0) * 0.6)
    opportunity_score = int(max(10, min(99, base_opportunity + opp_inventory + opp_velocity + opp_scale)))

    return {
        "financial_health_score": health_score,
        "composite_100": result["composite_100"],
        "health_grade": result["health_grade"],
        "risk_assessment": result["risk_assessment"],
        "opportunity_score": opportunity_score,
        "pillars": result["pillars"],
        "explainability": result["explainability"],
        "ai_insight": build_ai_insight(data, result),
        "business_need": predict_business_need(data, health_score),
        "ml_cross_check": ml_cross_check(data),
    }


# ---------------------------------------------------------------------------
# Simulated Account Aggregator handshake (in-process, no HTTP)
# ---------------------------------------------------------------------------
_MOCK_FIP = {
    "gst_avg_monthly_revenue": 1_450_000.0, "gst_filing_delay_days": 3,
    "upi_monthly_txns": 890, "upi_avg_txn_value": 1450.0,
    "aa_avg_bank_balance": 380_000.0, "aa_bounced_txns_6m": 1,
    "epfo_employee_count": 18, "business_vintage_years": 4,
    "inventory_growth_trend": 15.0,
}


def aa_consent_and_fetch(entity_name: str) -> dict:
    """Simulate the AA consent -> approve -> fetch handshake and return the data packet.

    In production this is: FIU raises consent -> AA notifies the borrower -> the
    borrower approves in their AA app -> the FIU fetches an FI data packet from the
    FIP. Here the three steps run in-process so the flow is demonstrable without a
    live sandbox.
    """
    handle = f"AA-{uuid.uuid4().hex[:10].upper()}"
    return {
        "consent_handle": handle,
        "status": "ACTIVE",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Simulated FIP via Account Aggregator",
        "entity_name": entity_name,
        "data": dict(_MOCK_FIP),
    }
