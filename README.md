# SmartDialer — Complete Hiring Assignment Prototype

A runnable SmartDialer prototype using the supplied synthetic collections dataset. Includes progressive and predictive dialing, a separate safety cap, two mock providers, event deduplication, dataset import, simulation, metrics, and tests.

## Dataset
The supplied dataset is included at `collections_30k_dataset/` beside `app/` and `requirements.txt`. The loader reads `borrowers.csv`, `accounts.csv`, `agents.csv`, `calls.csv`, `call_attempts.csv`, `campaigns.csv`, `daily_targeting.csv`, and `vendor_telephony.csv`. It deduplicates borrower IDs for import and uses maximum account DPD as a simple priority signal. The dataset is synthetic and intentionally contains data-quality anomalies.

## Run on Windows
Open PowerShell in the extracted `smartdialer_project` folder:
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Then open http://127.0.0.1:8000/docs.

## Run on Linux/macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Quick demo using Swagger
1. `GET /dataset/summary` to inspect the dataset.
2. `POST /dataset/import-borrowers?limit=100` to import sample borrower rows.
3. Create 3–5 agents using `POST /agents`, body `{"name":"Agent 1","team":"T1"}`.
4. Create a campaign using `POST /campaigns`, body `{"name":"Demo","mode":"progressive","provider":"A"}`.
5. Copy its `campaign_id`; call `POST /campaigns/{campaign_id}/dial` with `{"answer_rate":0.35,"avg_talk_seconds":120}`.
6. Inspect `/agents`, `/calls`, and `/metrics`.
7. Repeat with mode `predictive` and provider `B`.

Example simulation:
`POST /simulation/run?agents=10&borrowers=100&mode=predictive&answer_rate=0.5&avg_talk_seconds=90&provider=B`

## Tests
```bash
pytest -q
```

## Structure
- `app/main.py`: REST endpoints and validation.
- `app/services/engine.py`: state, dialing, safety cap, event handling, persistence and simulation.
- `app/services/dataset.py`: dataset summary and borrower import.
- `app/services/providers.py`: mock provider A (reliable) and B (flaky).
- `app/tests/`: capacity, idempotency and late-event tests.
- `docs/`: architecture and state-machine documentation.

## Design decisions and limitations
This is a simple modular monolith. A local JSON file makes the prototype easy to run without external services. An in-process lock protects concurrent requests within one process. For real multi-worker deployment, replace JSON persistence with PostgreSQL transactions, row-level locks and durable event storage. Predictive pacing is an explainable heuristic, not an ML model. Provider timeouts are treated as uncertain outcomes and retain reservations for reconciliation rather than blindly retrying. The mock providers do not place real calls. Production dialing would need consent, contact-time restrictions, suppression lists, audit logging and compliance review.
