# Paytm Vyapar Saathi
**Track 2: AI for Small Businesses | Agent Labs Buildathon (Phinite x Paytm)**

A multi-agent assistant for small Paytm merchants. It handles two everyday moments where a
merchant's trust in digital payments breaks down: a customer says they have paid but the Soundbox
stays silent, and a supplier wants money at 4 PM while tomorrow's loan EMI still has to be covered.

---

## The two problems

1. **Silent Soundbox or fake payment?** On a weak 2G link the Soundbox can announce a genuine payment
   seconds late. Fraudsters exploit the same moment with fake payment apps, old receipts, or a real
   receipt with the amount edited. The merchant has to decide on the spot.
2. **The 16:00 supplier bill.** The distributor wants ₹4,500 now. The merchant has ₹6,000 of today's
   collections still unsettled, and a ₹3,000 loan EMI is deducted from the next morning's settlement
   batch. Settling everything on demand pays the supplier but bounces the EMI.

## How it works

```
        payment claim / WhatsApp bill / settlement tap
                            │
                 ┌──────────▼───────────┐
                 │  Master Supervisor   │  routes events, keeps an audit trail
                 └──┬────────┬───────┬──┘
        ┌───────────┘        │       └──────────────┐
┌───────▼────────┐  ┌────────▼────────┐  ┌──────────▼─────────┐
│  Spoof Guard   │  │ Supplier Ledger │  │  Liquidity Engine  │
│ gateway + MQTT │  │ PII mask + bill │──▶ EMI-safe payment   │
│ checks         │  │ extraction      │  │ plan + maker-check │
└────────────────┘  └─────────────────┘  └──────────┬─────────┘
                                                    │ merchant approves
                                         ┌──────────▼─────────┐
                                         │ Signed, idempotent │
                                         │ settlement         │
                                         └────────────────────┘
```

| Agent | What it does | Code |
|---|---|---|
| Supervisor | One entry point (`handle_event`) for payment claims, bills and settlement taps; records every outcome | `agents/supervisor.py` |
| Spoof Guard | A claim is genuine only if the payment exists on the gateway, went to *this* Soundbox's merchant, is recent, and matches the amount on the customer's screen. Genuine but unacknowledged (no MQTT PUBACK) → "payment received, audio delayed" | `agents/spoof_guard.py`, `mock_backend/main.py` |
| Supplier Ledger | Masks card, Aadhaar, phone, bank account, PAN, IFSC and UPI IDs, then extracts total, vendor, invoice number, deadline and quantities. Any extracted amount that is not in the message text is rejected | `agents/supplier_ledger.py`, `agents/invoice_parser.py` |
| Liquidity Engine | Builds the payment plan below and re-checks it independently before anything is paid | `agents/liquidity_engine.py`, `agents/guardrails.py` |

### The payment plan

The EMI reserve is never touched. For a bill of `due`:

1. **Pay from balance** if `due ≤ balance − EMI`.
2. **Pay with an advance** otherwise, settling `balance − EMI` now and covering the gap with a short
   advance, but only if the gap fits both a pre-approved limit and the *conservative floor* of the
   forecast of tonight's sales (those sales repay the advance in the next settlement batch).
3. **Partial payment** otherwise: pay what is safe and tell the merchant how much to defer.

The forecast never approves anything by itself. In the demo the ₹4,500 Amul bill becomes
₹3,000 from the balance plus a ₹1,500 advance, and ₹3,000 stays for the EMI.

### Settlement safety

- Requests are signed with HMAC-SHA256 over the exact bytes sent plus a timestamp; forged, edited or
  stale requests are rejected.
- Each payout has one order ID and one idempotency key, reused on every retry, so a retry can never pay twice.
- After a bank timeout (504) the supervisor first asks for the order's status (the sandbox stand-in
  for an NPCI UDIR check) and only resends the identical request if the order never arrived.

## Forecaster results

The Liquidity Engine's PyTorch LSTM predicts sales from 16:00 to midnight from the last three days'
morning/evening sales and today's morning sales. Inputs are divided by the merchant's recent daily
average, so one model works for a small kirana and a large distributor.

Test period (last 15% of dates, held out; 2,200 samples), from `models/metrics.json`:

| Model | MAE (₹) | MAPE | R² |
|---|---:|---:|---:|
| **LSTM** | **1,84,364** | **16.9%** | **0.454** |
| Today's morning × recent evening/morning ratio | 2,30,100 | 20.2% | 0.080 |
| Mean of the last 3 evenings | 2,93,512 | 28.2% | −0.358 |
| Recent daily average − today's morning | 4,65,627 | 45.0% | −2.361 |

The conservative floor is 0.761 × the forecast (10th percentile of actual/forecast on the
validation period); actual evening sales were at or above it on 88.7% of test days.

**Read these numbers with care.** The training data is a synthetic retail sales dataset with no
time of day, so the morning/evening split is simulated (each day's morning share is drawn from
N(0.40, 0.05)). The table shows that the pipeline is sound and beats simple baselines on held-out
data; it says nothing about real merchants. Real Paytm transaction histories would be needed for that.
Reproduce with `python scripts/train_lstm.py` (seeded, about 10 seconds on CPU).

> An earlier version of this repository reported "94% validation accuracy". That figure came from a
> formula that capped the printed value between 92.5% and 94.8%, with no validation split, and has been
> withdrawn together with the model it described.

## What is real and what is simulated

| Part | Status |
|---|---|
| Spoof checks, payment plan, maker-checker, PII masking, bill extraction, signing, idempotency | Real logic, covered by tests |
| Forecaster | Real model and evaluation; synthetic morning/evening split (see above) |
| Paytm gateway, Soundbox MQTT telemetry, settlement API, NPCI UDIR status | Simulated by the FastAPI sandbox in `mock_backend/` |
| LLM agents in `phinite_schemas/agent_graph.yaml` | Specification for Phinite; not executed in this repo. The rule-based extractor and `validate_extraction` are the offline path and the checker for an LLM extractor |
| Advance / credit decision | Mock limit; a real advance needs Paytm Lending approval and merchant consent |

## Run it

```bash
pip install -r requirements-dev.txt

# 1. Backend (sandbox gateway + agents' API)
python -m uvicorn mock_backend.main:app --port 8000      # or start_backend.bat

# 2a. Terminal demo
python run_demo.py                                        # or run_demo.bat

# 2b. Live merchant app
streamlit run streamlit_app.py                            # http://localhost:8501

# Tests (no server needed)
python -m pytest -q
```

With Docker: `docker compose up --build`, then open http://localhost:8501.

Settings come from environment variables (see `.env.example`): `VS_BACKEND_URL`, `VS_MERCHANT_ID`
and `VS_MERCHANT_SIGNING_KEY`. The default signing key only works against the local sandbox.

## Project layout

```
agents/           supervisor, three workers, guardrails (PII, payment plan, signing), bill parser
ml/forecaster.py  LSTM model, scale-free features, loading and prediction
mock_backend/     FastAPI sandbox (gateway, telemetry, settlement, notifications, metrics)
scripts/          train_lstm.py
models/           evening_lstm.pt and metrics.json
phinite_schemas/  Phinite agent graph and tool schemas
tests/            pytest suite (backend, agents, parser, forecaster)
submission/       pitch script and deck generator
```

## Data

`datasets/synthetic_sales_data_400k.csv`: a synthetic retail sales dataset (400,000 rows, 2023–2024)
downloaded from Kaggle. Each of its 20 region-and-sales-rep combinations is treated as one merchant.
