"""
MSME Financial Health Scorecard — glass-box scoring engine
-----------------------------------------------------------
A fully transparent, rule-based credit scorecard built on alternate data
(GST, UPI, Account Aggregator, EPFO). Every point in the final 300-900 score
is traceable to a named pillar, a named sub-factor, and an auditable rule.

Design goal: a bank credit officer can reconstruct *why* an applicant scored
what they scored, by hand, from the same inputs. No black box.

Structure
---------
Five weighted pillars, each scored 0-100 from the raw inputs, then combined:

    Pillar                     Weight   What it captures
    ------------------------   ------   ----------------------------------------
    Revenue Health              0.28    Scale + compliance discipline of turnover
    Cash-Flow Stability         0.24    Buffer depth vs. outflow, bounce history
    Banking Discipline          0.20    Bounced debits, filing punctuality
    Workforce Stability         0.14    EPFO headcount as a going-concern signal
    Growth Momentum             0.14    Inventory/capex trend + txn velocity

Each pillar returns its 0-100 sub-score AND the sub-factor breakdown that
produced it, so the UI and the /score response can show real attribution.

The weighted pillar total (0-100) is then mapped onto the familiar 300-900
bureau-style band via a linear transform, so the output is comparable in shape
to scores lenders already reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _linear(value: float, at_zero: float, at_full: float, full_value: float) -> float:
    """Map `value` linearly so that value=0 -> at_zero and value=full_value -> at_full."""
    if full_value <= 0:
        return at_zero
    frac = value / full_value
    return at_zero + (at_full - at_zero) * frac


@dataclass
class SubFactor:
    name: str
    points: float          # contribution to this pillar's 0-100 score
    max_points: float      # the most this sub-factor could contribute
    detail: str            # human-readable reason

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "points": round(self.points, 1),
            "max_points": round(self.max_points, 1),
            "detail": self.detail,
        }


@dataclass
class Pillar:
    key: str
    label: str
    weight: float
    score: float                              # 0-100
    factors: list[SubFactor] = field(default_factory=list)

    @property
    def weighted_contribution(self) -> float:
        return self.score * self.weight

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "weight": self.weight,
            "score": round(self.score, 1),
            "weighted_contribution": round(self.weighted_contribution, 2),
            "factors": [f.as_dict() for f in self.factors],
        }


# ---------------------------------------------------------------------------
# The five pillars
# ---------------------------------------------------------------------------
def _pillar_revenue_health(d: dict) -> Pillar:
    """Scale and compliance discipline of GST-reported turnover."""
    rev = d["gst_avg_monthly_revenue"]
    delay = d["gst_filing_delay_days"]

    # Sub-factor A: turnover scale (max 65). Saturates at ~30L/month.
    scale_pts = _clamp(_linear(rev, 0, 65, full_value=3_000_000), 0, 65)
    scale = SubFactor(
        "Turnover scale",
        scale_pts,
        65,
        f"Avg monthly GST turnover of Rs {rev:,.0f}.",
    )

    # Sub-factor B: filing punctuality (max 35). 0-day delay = full marks,
    # decays to 0 by ~45 days late.
    punctuality_pts = _clamp(_linear(45 - delay, 0, 35, full_value=45), 0, 35)
    punctuality = SubFactor(
        "Filing punctuality",
        punctuality_pts,
        35,
        f"Average GST return filing delay of {delay} day(s).",
    )

    score = scale.points + punctuality.points
    return Pillar("revenue_health", "Revenue Health", 0.28, score, [scale, punctuality])


def _pillar_cashflow_stability(d: dict) -> Pillar:
    """Depth of liquid buffer relative to monthly outflow proxy."""
    balance = d["aa_avg_bank_balance"]
    rev = d["gst_avg_monthly_revenue"]
    bounces = d["aa_bounced_txns_6m"]

    # Buffer months: how many months of revenue-scale outflow the balance covers.
    outflow_proxy = max(1.0, rev * 0.7)   # assume ~70% of turnover leaves as outflow
    buffer_months = balance / outflow_proxy

    # Sub-factor A: liquidity buffer (max 70). 1.5+ months of cover = full marks.
    buffer_pts = _clamp(_linear(buffer_months, 0, 70, full_value=1.5), 0, 70)
    buffer = SubFactor(
        "Liquidity buffer",
        buffer_pts,
        70,
        f"Avg balance covers ~{buffer_months:.2f} month(s) of estimated outflow.",
    )

    # Sub-factor B: outflow reliability (max 30), penalised by bounces.
    reliability_pts = _clamp(30 - bounces * 10, 0, 30)
    reliability = SubFactor(
        "Outflow reliability",
        reliability_pts,
        30,
        f"{bounces} bounced debit(s) in the last 6 months."
        if bounces
        else "No bounced debits in the last 6 months.",
    )

    score = buffer.points + reliability.points
    return Pillar("cashflow_stability", "Cash-Flow Stability", 0.24, score, [buffer, reliability])


def _pillar_banking_discipline(d: dict) -> Pillar:
    """Repayment-adjacent behaviour: bounces and filing discipline combined."""
    bounces = d["aa_bounced_txns_6m"]
    delay = d["gst_filing_delay_days"]

    # Sub-factor A: bounce record (max 60). Each bounce is expensive here.
    bounce_pts = _clamp(60 - bounces * 20, 0, 60)
    bounce = SubFactor(
        "Bounce record",
        bounce_pts,
        60,
        f"{bounces} dishonoured transaction(s) on record."
        if bounces
        else "Clean dishonour record.",
    )

    # Sub-factor B: obligation punctuality (max 40) via filing delay proxy.
    punctual_pts = _clamp(_linear(30 - delay, 0, 40, full_value=30), 0, 40)
    punctual = SubFactor(
        "Obligation punctuality",
        punctual_pts,
        40,
        f"Statutory filing delay of {delay} day(s) used as a punctuality proxy.",
    )

    score = bounce.points + punctual.points
    return Pillar("banking_discipline", "Banking Discipline", 0.20, score, [bounce, punctual])


def _pillar_workforce_stability(d: dict) -> Pillar:
    """EPFO headcount as a going-concern / formalisation signal."""
    heads = d["epfo_employee_count"]
    vintage = d.get("business_vintage_years", 0)

    # Sub-factor A: payroll base (max 70). Saturates at ~40 employees.
    payroll_pts = _clamp(_linear(heads, 0, 70, full_value=40), 0, 70)
    payroll = SubFactor(
        "Payroll base",
        payroll_pts,
        70,
        f"{heads} active employee(s) on EPFO records.",
    )

    # Sub-factor B: operating vintage (max 30). Saturates at 10 years.
    vintage_pts = _clamp(_linear(vintage, 0, 30, full_value=10), 0, 30)
    vintage_f = SubFactor(
        "Operating vintage",
        vintage_pts,
        30,
        f"{vintage} year(s) in operation.",
    )

    score = payroll.points + vintage_f.points
    return Pillar("workforce_stability", "Workforce Stability", 0.14, score, [payroll, vintage_f])


def _pillar_growth_momentum(d: dict) -> Pillar:
    """Forward-looking demand signal: inventory build-up and txn velocity."""
    inv = d.get("inventory_growth_trend", 0.0)
    txns = d["upi_monthly_txns"]
    ticket = d["upi_avg_txn_value"]

    # Sub-factor A: inventory/capex trend (max 55). Saturates at +30% growth,
    # floors at 0 for contraction.
    inv_pts = _clamp(_linear(inv, 0, 55, full_value=30), 0, 55)
    inv_f = SubFactor(
        "Inventory / capex trend",
        inv_pts,
        55,
        f"Quarterly inventory/capex growth of {inv:.0f}%.",
    )

    # Sub-factor B: transaction velocity (max 45) via monthly UPI throughput.
    throughput = txns * ticket
    velocity_pts = _clamp(_linear(throughput, 0, 45, full_value=2_000_000), 0, 45)
    velocity = SubFactor(
        "Transaction velocity",
        velocity_pts,
        45,
        f"{txns} UPI txns/month at Rs {ticket:,.0f} avg = Rs {throughput:,.0f} throughput.",
    )

    score = inv_f.points + velocity.points
    return Pillar("growth_momentum", "Growth Momentum", 0.14, score, [inv_f, velocity])


_PILLAR_BUILDERS: list[Callable[[dict], Pillar]] = [
    _pillar_revenue_health,
    _pillar_cashflow_stability,
    _pillar_banking_discipline,
    _pillar_workforce_stability,
    _pillar_growth_momentum,
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def compute_scorecard(data: dict) -> dict:
    """Run the full glass-box scorecard and return a structured, auditable result."""
    pillars = [build(data) for build in _PILLAR_BUILDERS]

    # Weighted composite on a 0-100 scale.
    composite_100 = sum(p.weighted_contribution for p in pillars)

    # Map 0-100 -> 300-900 bureau-style band.
    final_score = int(round(300 + composite_100 * 6.0))
    final_score = max(300, min(900, final_score))

    grade = (
        "A" if final_score >= 740
        else "B" if final_score >= 620
        else "C" if final_score >= 500
        else "D"
    )
    risk_tier = (
        "Low Risk" if final_score >= 700
        else "Medium Risk" if final_score >= 520
        else "High Risk"
    )

    # Build real, ranked explainability from the pillar sub-factors: each factor's
    # "headroom lost" is (max_points - points) scaled by pillar weight. That tells
    # us which levers actually cost this applicant the most points.
    positives: list[dict] = []
    negatives: list[dict] = []
    for p in pillars:
        for f in p.factors:
            earned_share = f.points * p.weight * 6.0            # points on the 300-900 scale
            lost_share = (f.max_points - f.points) * p.weight * 6.0
            if earned_share >= lost_share:
                positives.append(
                    {
                        "factor": f"{p.label}: {f.name}",
                        "impact": f"+{earned_share:.0f} pts",
                        "detail": f.detail,
                        "_rank": earned_share,
                    }
                )
            else:
                negatives.append(
                    {
                        "factor": f"{p.label}: {f.name}",
                        "impact": f"-{lost_share:.0f} pts",
                        "detail": f.detail,
                        "_rank": lost_share,
                    }
                )

    positives.sort(key=lambda x: x.pop("_rank"), reverse=True)
    negatives.sort(key=lambda x: x.pop("_rank"), reverse=True)

    return {
        "financial_health_score": final_score,
        "composite_100": round(composite_100, 1),
        "health_grade": grade,
        "risk_assessment": risk_tier,
        "pillars": [p.as_dict() for p in pillars],
        "explainability": {
            "positive": positives[:4],
            "negative": negatives[:4],
        },
    }
