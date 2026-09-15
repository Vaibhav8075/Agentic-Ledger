# Paytm Vyapar Saathi
**Track 2: AI for Small Businesses | Agent Labs Buildathon (Phinite x Paytm)**

## Elevator Pitch
Paytm Vyapar Saathi is an autonomous multi-agent system built on the Phinite OS. It acts as an invisible guardian and financial manager for small retail merchants (SMBs). It intercepts Soundbox payment fraud in real-time and uses Deep Learning (PyTorch LSTM) to predict a merchant's future evening revenue, dynamically underwriting instant micro-loans so they can pay suppliers even when their current bank balance is zero.

---

## The Problems We Are Solving

Most Fintech happy-paths break in the real world. We are solving two critical edge cases for the everyday Paytm merchant:

1. **The Spoof & Lag Problem (Security & Trust):** 
   When a customer pays but the Soundbox remains silent due to network congestion or 4G signal drops, the merchant panics, thinking the customer is using a fake "Spoof" app.
2. **The 4:00 PM Liquidity Crunch (Cashflow):** 
   A merchant has INR 0 in their bank account at 4 PM, but the FMCG distributor (e.g., Amul) is standing at their shop demanding INR 4,500 for milk crates. The merchant has a Paytm loan EMI due the next morning, meaning their funds are locked. A traditional banking algorithm would block the payment, forcing the merchant to lose their inventory.

---

## Our Solution: The Multi-Agent Architecture

We solved this using a Swarm of 4 Phinite Agents working together in the background, communicating with a custom FastAPI backend and a PyTorch Deep Learning model.

### 1. Master Supervisor Agent (The Router)
- **Role:** Ingests real-time events (Soundbox MQTT telemetry pings, incoming WhatsApp Webhook messages).
- **Logic:** Decides whether the event is a security issue (routes to Spoof Guard) or a financial issue (routes to Supplier Ledger).

### 2. Spoof Guard Agent (The Guardian)
- **Role:** Analyzes transaction hashes in under 200ms.
- **Logic:** 
  - If a customer flashes a fake payment app, it instantly detects the missing gateway hash and pushes a FRAUD ALERT to the merchant's phone.
  - If it's a real payment but the 4G network is lagging/congested, it checks the broker telemetry, confirms the payment is mathematically secure, and pushes a "Payment Safe, Audio Delayed" notification to calm the merchant.

### 3. Supplier Ledger Agent (The Data Extractor)
- **Role:** Processes unstructured vendor bills (e.g., a WhatsApp message from the Amul distributor).
- **Logic:** Uses Phinite-compliant guardrails to redact/mask sensitive PII (like bank account numbers), extracts the total liability (INR 4,500), and passes it to the Liquidity Engine.

### 4. Liquidity Engine Agent (The Deep Learning Brain)
- **Role:** Evaluates merchant cash-flow risk.
- **Logic:** Instead of using rigid subtraction logic (Balance - Bill = Denied), it connects to our custom PyTorch LSTM Neural Network. The AI looks at the merchant's transaction velocity and predicts they will earn INR 8,450 during tonight's evening rush. Because the AI mathematically guarantees future revenue, the agent auto-approves the Amul payment instantly, saving the merchant's business.

---

## Tech Stack & Technical Details
- **Orchestration:** Phinite OS Visual Agent Graph
- **Deep Learning:** PyTorch (LSTM trained on 400,000 rows of Kaggle retail data with Sklearn MinMax scaling).
- **Backend Simulation:** FastAPI & Uvicorn (Handles Bank 504 timeouts, Idempotency, and Double-Debit protection).
- **Frontend / Demo:** Streamlit (Simulates the Merchant's Paytm for Business mobile app).
- **Infrastructure:** Fully containerized using Docker & Docker-Compose.

---

## How to Run the System

**Production Environment (Docker)**
1. Open terminal in the root directory.
2. Run `docker-compose up --build`
3. Access the dashboard at `http://localhost:8501`.

**Local Development (Python)**
1. Install dependencies: `pip install -r requirements.txt`
2. Start the Backend API: `start_backend.bat`
3. Start the Frontend UI: `streamlit run streamlit_app.py`
4. Access the dashboard at `http://localhost:8501`.
