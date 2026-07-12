"""
MSME Financial Health Card — Scoring API (v2)
----------------------------------------------
Turns alternate-data signals (GST, UPI, Account Aggregator, EPFO) into a
transparent, multidimensional financial health score for New-to-Credit /
New-to-Bank MSMEs.

What changed in v2
------------------
- The score is now produced by a **glass-box weighted scorecard** (scorecard.py):
  five pillars, each 0-100, combined with visible weights into a 300-900 band.
  Every point is auditable back to a named sub-factor. This replaces the opaque
  RandomForest as the source of truth.
- The RandomForest is retained only as a clearly-labelled, secondary
  **ML cross-check** on the /score response. It is NOT the decision score.
  (In testing it barely discriminates across inputs, so it must not be relied on.)
- Added simulated **Account Aggregator (AA)** and **OCEN** endpoints that mimic
  the consent -> fetch -> disburse-intent handshake of India's credit rails, so
  the data-ingestion story is demonstrable end to end without live sandbox access.

Run with: python main.py    (docs at http://127.0.0.1:8000/docs)
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

import joblib
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from scorecard import compute_scorecard

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("msme_health")

MODEL_PATH = os.getenv("MODEL_PATH", "msme_health_model.pkl")

app = FastAPI(
    title="MSME Financial Health Card API",
    description=(
        "Transparent scoring engine that turns GST, UPI, Account Aggregator and "
        "EPFO alternate data into a multidimensional financial health score, a "
        "risk tier, an auditable pillar breakdown, and a matched credit product. "
        "Includes simulated Account Aggregator and OCEN rails."
    ),
    version="2.0.0",
)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Optional ML cross-check model (secondary signal only)
# ---------------------------------------------------------------------------
ml_model = None
ML_FEATURES: list[str] = []
try:
    ml_model = joblib.load(MODEL_PATH)
    ML_FEATURES = list(getattr(ml_model, "feature_names_in_", []))
    logger.info("ML cross-check model loaded. Features: %s", ML_FEATURES)
except FileNotFoundError:
    logger.warning("ML cross-check model not found at '%s' — scorecard runs without it.", MODEL_PATH)
except Exception as exc:  # noqa: BLE001
    logger.warning("ML cross-check model failed to load (%s) — scorecard runs without it.", exc)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class MSMEDataPayload(BaseModel):
    """Alternate-data inputs used to compute the financial health score."""

    gst_avg_monthly_revenue: float = Field(..., ge=0, description="Average monthly GST turnover, INR")
    gst_filing_delay_days: int = Field(..., ge=0, description="Average delay in GST return filing, days")
    upi_monthly_txns: int = Field(..., ge=0, description="Monthly UPI transaction count")
    upi_avg_txn_value: float = Field(..., ge=0, description="Average UPI ticket size, INR")
    aa_avg_bank_balance: float = Field(..., ge=0, description="Average bank balance via Account Aggregator, INR")
    aa_bounced_txns_6m: int = Field(..., ge=0, description="Bounced debits/cheques in the last 6 months")
    epfo_employee_count: int = Field(..., ge=0, description="Active payroll headcount per EPFO records")
    business_vintage_years: int = Field(default=5, ge=0, description="Years in operation")
    inventory_growth_trend: float = Field(default=0.0, description="Quarterly inventory/capex growth, %")


class ConsentRequest(BaseModel):
    """Simulated Account Aggregator consent request (FIU -> AA)."""

    entity_name: str = Field(..., description="Registered name of the MSME requesting the pull")
    mobile: str = Field(default="", description="Linked mobile for consent notification (simulated)")


# ---------------------------------------------------------------------------
# Business-need matching (unchanged in spirit, tightened thresholds)
# ---------------------------------------------------------------------------
def predict_business_need(data: MSMEDataPayload, health_score: int) -> dict:
    if data.inventory_growth_trend > 12 and health_score > 600:
        return {"need": "Inventory & asset scaling", "confidence": "94%", "product": "Smart Trade Inventory Line"}
    if data.upi_monthly_txns > 600 and data.aa_avg_bank_balance < 400_000:
        return {"need": "Working-capital cash-flow gap", "confidence": "89%", "product": "Express Cash-Flow Overdraft"}
    if health_score < 500:
        return {"need": "Pre-credit strengthening", "confidence": "71%", "product": "Guided Readiness Programme"}
    return {"need": "General capital expenditure", "confidence": "76%", "product": "Corporate Growth Credit Line"}


def ml_cross_check(payload: MSMEDataPayload) -> dict | None:
    """Run the secondary ML model, if available, purely as a comparison signal."""
    if ml_model is None or not ML_FEATURES:
        return None
    try:
        raw = payload.model_dump()
        row = {f: raw[f] for f in ML_FEATURES if f in raw}
        pred = float(ml_model.predict(pd.DataFrame([row]))[0])
        pred = int(max(300, min(900, pred)))
        return {
            "ml_score": pred,
            "label": "Experimental ML cross-check (RandomForest)",
            "note": "Secondary signal only. The scorecard above is the decision score.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML cross-check failed: %s", exc)
        return None


def build_ai_insight(payload: MSMEDataPayload, result: dict) -> str:
    lines = []
    weakest = min(result["pillars"], key=lambda p: p["score"])
    strongest = max(result["pillars"], key=lambda p: p["score"])
    lines.append(f"Strongest pillar is {strongest['label']} ({strongest['score']:.0f}/100).")
    lines.append(f"Weakest is {weakest['label']} ({weakest['score']:.0f}/100) — the primary lever to improve.")
    if payload.aa_bounced_txns_6m > 0:
        lines.append(f"{payload.aa_bounced_txns_6m} bounced transaction(s) are dragging Banking Discipline.")
    else:
        lines.append("Clean dishonour record supports the risk tier.")
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Core scoring endpoint
# ---------------------------------------------------------------------------
@app.post("/api/v1/score")
def evaluate_msme_profile(payload: MSMEDataPayload):
    try:
        result = compute_scorecard(payload.model_dump())
        health_score = result["financial_health_score"]

        base_opportunity = 45
        opp_inventory = max(0, payload.inventory_growth_trend * 1.4)
        opp_velocity = min(
            25,
            ((payload.upi_monthly_txns * payload.upi_avg_txn_value) / max(1, payload.aa_avg_bank_balance)) * 4,
        )
        opp_scale = min(15, payload.epfo_employee_count * 0.6)
        opportunity_score = int(max(10, min(99, base_opportunity + opp_inventory + opp_velocity + opp_scale)))

        return {
            "financial_health_score": health_score,
            "composite_100": result["composite_100"],
            "health_grade": result["health_grade"],
            "risk_assessment": result["risk_assessment"],
            "opportunity_score": opportunity_score,
            "pillars": result["pillars"],
            "explainability": result["explainability"],
            "ai_insight": build_ai_insight(payload, result),
            "business_need": predict_business_need(payload, health_score),
            "ml_cross_check": ml_cross_check(payload),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scoring failed")
        raise HTTPException(status_code=400, detail=f"Scoring failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Simulated Account Aggregator rail
# ---------------------------------------------------------------------------
# In production this is: FIU raises consent -> AA notifies user -> user approves
# at their AA app -> FIU fetches an FI data packet from the FIP. Here we simulate
# each step so the ingestion flow is demonstrable end to end. Consents live in
# memory only, for the duration of the demo.
_CONSENTS: dict[str, dict] = {}

# A tiny mock FIP dataset keyed loosely by name, so "fetch" returns believable,
# pre-filled alternate data instead of the user typing everything.
_MOCK_FIP = {
    "default": {
        "gst_avg_monthly_revenue": 1_450_000.0, "gst_filing_delay_days": 3,
        "upi_monthly_txns": 890, "upi_avg_txn_value": 1450.0,
        "aa_avg_bank_balance": 380_000.0, "aa_bounced_txns_6m": 1,
        "epfo_employee_count": 18, "business_vintage_years": 4,
        "inventory_growth_trend": 15.0,
    }
}


@app.post("/api/v1/aa/consent")
def aa_raise_consent(req: ConsentRequest):
    """Step 1 — raise a (simulated) AA consent request and return a handle."""
    handle = f"AA-{uuid.uuid4().hex[:10].upper()}"
    _CONSENTS[handle] = {
        "entity_name": req.entity_name,
        "status": "PENDING",
        "raised_at": datetime.now(timezone.utc).isoformat(),
        "fi_types": ["DEPOSIT", "GST_RETURN", "UPI_STATEMENT", "EPFO_RECORD"],
    }
    return {
        "consent_handle": handle,
        "status": "PENDING",
        "message": "Consent request raised. Awaiting borrower approval at their AA app.",
    }


@app.post("/api/v1/aa/consent/{handle}/approve")
def aa_approve_consent(handle: str):
    """Step 2 — borrower approves the consent (simulated tap in their AA app)."""
    consent = _CONSENTS.get(handle)
    if not consent:
        raise HTTPException(status_code=404, detail="Unknown consent handle.")
    consent["status"] = "ACTIVE"
    consent["approved_at"] = datetime.now(timezone.utc).isoformat()
    return {"consent_handle": handle, "status": "ACTIVE", "message": "Consent approved by borrower."}


@app.get("/api/v1/aa/consent/{handle}/fetch")
def aa_fetch_data(handle: str):
    """Step 3 — fetch the FI data packet from the (mock) FIP under an active consent."""
    consent = _CONSENTS.get(handle)
    if not consent:
        raise HTTPException(status_code=404, detail="Unknown consent handle.")
    if consent["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Consent is not ACTIVE. Approve it first.")
    packet = dict(_MOCK_FIP["default"])
    return {
        "consent_handle": handle,
        "entity_name": consent["entity_name"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Simulated FIP via Account Aggregator",
        "data": packet,
    }


# ---------------------------------------------------------------------------
# Simulated OCEN disbursal-intent rail
# ---------------------------------------------------------------------------
@app.post("/api/v1/ocen/loan-intent")
def ocen_loan_intent(payload: MSMEDataPayload):
    """Given a scored profile, emit a simulated OCEN loan-application intent that a
    Loan Service Provider (LSP) would forward to lenders."""
    scored = compute_scorecard(payload.model_dump())
    score = scored["financial_health_score"]
    need = predict_business_need(payload, score)
    approx_limit = int(min(5_000_000, payload.gst_avg_monthly_revenue * 2.5 * (score / 900)))
    return {
        "ocen_request_id": f"OCEN-{uuid.uuid4().hex[:8].upper()}",
        "health_score": score,
        "risk_tier": scored["risk_assessment"],
        "recommended_product": need["product"],
        "indicative_limit": approx_limit,
        "status": "FORWARDED_TO_LENDERS",
        "note": "Simulated OCEN intent. No real disbursal occurs.",
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "scorecard": "active",
        "ml_cross_check_loaded": ml_model is not None,
        "ml_features": ML_FEATURES,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
