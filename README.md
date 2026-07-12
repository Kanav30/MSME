# MSME Financial Health Card

A transparent, multidimensional financial health score for New-to-Credit (NTC)
and New-to-Bank (NTB) MSMEs, built entirely on alternate data — GST, UPI,
Account Aggregator (AA), and EPFO — instead of traditional financial statements.

Built for the IDBI problem statement on expanding credit access for
credit-invisible MSMEs using alternate data and the ULI / OCEN / AA rails.

## The problem

Traditional MSME credit evaluation relies on financial documents many small
businesses do not maintain, which drives high rejection rates for otherwise
viable borrowers and slows financial inclusion. Rich alternate data already
exists (GST returns, UPI flows, bank statements via AA, EPFO records), but there
is no unified framework that turns it into a single, explainable, lender-ready
assessment. This project is that framework.

## What makes the score defensible

The score is produced by a **glass-box weighted scorecard**, not a black box.
Five pillars are each scored 0–100 from the raw inputs, then combined with
visible weights into the familiar 300–900 band:

| Pillar               | Weight | Captures                                         |
|----------------------|:------:|--------------------------------------------------|
| Revenue Health       |  28%   | Turnover scale + GST filing discipline           |
| Cash-Flow Stability  |  24%   | Liquidity buffer depth, outflow reliability      |
| Banking Discipline   |  20%   | Bounce record + obligation punctuality           |
| Workforce Stability  |  14%   | EPFO headcount + operating vintage               |
| Growth Momentum      |  14%   | Inventory/capex trend + UPI throughput           |

Every point traces back to a named pillar, a named sub-factor, and an auditable
rule (`scorecard.py`). A credit officer can reconstruct any score by hand from
the same inputs — which is exactly how real credit scorecards are built and
governed. The explainability breakdown shown in the UI is computed from these
real sub-factor contributions, ranked by how many points each lever earned or
cost.

## Architecture

- **`scorecard.py`** — the transparent scoring engine. Five pillars, sub-factor
  breakdowns, weighted composite, 300–900 mapping, and ranked real
  explainability. No external model dependency.
- **`main.py`** — FastAPI service exposing:
  - `POST /api/v1/score` — full assessment: score, grade, risk tier, pillar
    breakdown, explainability, matched credit product, and a secondary ML
    cross-check.
  - `POST /api/v1/aa/consent` → `/{handle}/approve` → `GET /{handle}/fetch` —
    a **simulated Account Aggregator** consent → approve → fetch handshake that
    mirrors the real FIU/AA/FIP flow and returns a pre-filled alternate-data
    packet.
  - `POST /api/v1/ocen/loan-intent` — a **simulated OCEN** loan-application
    intent an LSP would forward to lenders, with an indicative limit derived
    from the score.
  - `GET /health` — liveness and model status.
- **`app.py`** — Streamlit console with two roles:
  - **MSME self-assessment** — fetch data through the simulated AA consent flow,
    view the five-pillar score, run what-if scenarios, generate a certificate.
  - **Credit Officer console** — prioritized lead queue and per-borrower
    deep-dive with pillar-level explainability.

## The ML model is a labelled secondary signal, on purpose

The repository includes a `RandomForestRegressor` (`msme_health_model.pkl`).
On inspection it barely discriminates across inputs (near-identical output for
minimum vs. maximum feature values), so it is **not** used as the decision
score. It is retained only as a clearly-labelled "experimental ML cross-check"
shown alongside the scorecard, so the AI/ML dimension is present without staking
a credit decision on a model that does not separate applicants. The transparent
scorecard is the source of truth.

## Running locally

```bash
pip install -r requirements.txt

# Terminal 1 — API (serves on http://127.0.0.1:8000, docs at /docs)
python main.py

# Terminal 2 — UI (serves on http://localhost:8501)
streamlit run app.py
```

Point the UI at a non-default API location when deployed separately:

```bash
export MSME_API_URL="https://your-api-host"
streamlit run app.py
```

Credit Officer demo access code: `idbi2026` (override with `RM_DEMO_ACCESS_CODE`).

## Alignment to the problem statement

- **Aggregates alternate data** — GST, UPI, AA, EPFO feed the five pillars.
- **Multidimensional score** — five explicit pillars, not a single opaque number.
- **Visualizes strengths and risks** — pillar bars plus ranked driver/detractor
  factors.
- **Integrates with ULI / OCEN / AA** — demonstrated end to end via the
  simulated AA consent flow and OCEN loan-intent endpoints.
- **Near real-time assessment** — a scored result returns on each input change.
- **Expands onboarding, improves portfolio quality** — the officer console
  surfaces credit-invisible but strong borrowers and flags weak ones for review.

## Honest limitations (state these to judges)

- **Data sources are simulated.** The AA/OCEN endpoints and the fetched data
  packet are mocks that mirror the real handshake; a production build wires in
  live GSTN APIs, the AA framework (Sahamati), UPI switch data, EPFO records,
  and OCEN via a real LSP.
- **Officer login is a static code**, meant only to separate the two demo views,
  not real bank IAM/SSO.
- **The bundled RandomForest is weak** and is deliberately demoted to a
  secondary cross-check (see above).
- **Certificate export** uses the browser print dialog rather than a server-side
  PDF renderer.

## Next steps toward production

- Live AA (Sahamati) / GSTN / EPFO / OCEN ingestion replacing the mock layer.
- Pillar weights calibrated and back-tested against realised default outcomes.
- Bank IAM/SSO, audit logging, and consent-artefact storage for governance.
- Score monitoring for population and characteristic drift.
