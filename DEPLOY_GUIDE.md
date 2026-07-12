## Deploying the MSME Financial Health Card (Streamlit Community Cloud)

This gets you both submission-form fields filled: the **GitHub Repository Link**
and the **Deployment Link**. The app is self-contained — the Streamlit UI now
runs the scoring engine in-process, so there is no separate backend to host or
keep awake.

Total time: ~20 minutes. You need a GitHub account (you have one) and a browser.

---

### Part 1 — Push the code to GitHub  (fills the "GitHub Repository Link" field)

You can do this entirely in the browser — no Git install needed.

1. Go to https://github.com/new
2. Repository name: `msme-financial-health-card`
3. Set it to **Public** (the form asks for a public repo).
4. Do NOT tick "Add a README" (you already have one). Click **Create repository**.
5. On the next page, click **"uploading an existing file"** (the link in the
   "…or upload an existing file" line).
6. Drag in every file from the `msme-health-card-deploy` folder:
   `app.py`, `scoring_core.py`, `scorecard.py`, `main.py`,
   `requirements.txt`, `README.md`, `msme_health_model.pkl`, `.gitignore`
7. Scroll down, click **Commit changes**.

Your repo URL is now:
`https://github.com/<your-username>/msme-financial-health-card`
→ paste this into the **GitHub Repository Link** field.

---

### Part 2 — Deploy to Streamlit Community Cloud  (fills the "Deployment Link" field)

1. Go to https://share.streamlit.io and click **Sign in** → **Continue with GitHub**.
   Authorize Streamlit to read your repositories.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `<your-username>/msme-financial-health-card`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. (Optional) Click **Advanced settings** → set Python version to **3.11** or
   **3.12** for the smoothest install.
5. Click **Deploy**. First build takes 2–5 minutes while it installs packages.
6. When it finishes you get a public URL like
   `https://msme-financial-health-card.streamlit.app`
   → paste this into the **Deployment Link** field.

---

### Part 3 — Test it before you submit

Open your `.streamlit.app` URL in an incognito window (so you see what a judge
sees) and confirm:

- The login screen loads with the two role cards.
- **Enter as MSME** → click **Fetch via Account Aggregator** → fields populate
  and a score with the five pillars appears.
- The **Certificate** tab renders.
- Back on login, **Credit Officer Console** with code `idbi2026` → the priority
  queue and borrower deep-dive both load.

If the score responds when you change inputs and the pillars redraw, you're done.

---

### Notes for your submission / demo

- **The "Proof of Concept PPT" field wants a PDF.** Export your filled deck:
  in PowerPoint, File → Save As / Export → PDF. Keep it under 5 MB.
- The Credit Officer demo code is `idbi2026`. If you want to change it, add a
  secret named `RM_DEMO_ACCESS_CODE` in the Streamlit app's
  **Settings → Secrets** (format: `RM_DEMO_ACCESS_CODE = "yourcode"`), then
  mention the code in your demo notes.
- `main.py` (the FastAPI service) is still in the repo and still runs locally
  with `python main.py`. The deployed app doesn't use it — it calls the same
  scoring engine (`scorecard.py`) directly through `scoring_core.py`, so the
  math is identical. If a judge asks, the API layer is real and demonstrable
  locally; the hosted demo runs the UI self-contained purely for reliability.

---

### If the build fails

- **"Error installing requirements"** → open **Manage app** (bottom-right of the
  deployed app) to read the log. Almost always a Python-version mismatch; set
  3.11 or 3.12 in Advanced settings and reboot the app.
- **App loads but scoring errors** → confirm `msme_health_model.pkl` actually
  uploaded to the repo (it's ~7 MB; GitHub's browser upload handles it, but
  check it's listed in your repo file view). The app still runs without it —
  the ML cross-check just won't show — but the file should be there.
