# Paytm Vyapar Saathi - 3-Minute Hackathon Pitch Script

## Slide 1: The Problem (0:00 - 0:45)
**Speaker:** 
"Hello Judges. We built Paytm Vyapar Saathi on the Phinite OS. We are tackling two critical problems for the everyday Paytm merchant that exist *outside* of the happy path:
1. **The Spoof & Lag Problem:** When a customer pays, but the Soundbox is silent because of a 2G network drop. The merchant panics, thinking it's a Spoof App. 
2. **The 4:00 PM Liquidity Crunch:** The merchant has ₹0 in their bank account at 4 PM, but the Amul distributor is demanding ₹4,500 for milk crates. The merchant can't pay because their money is locked up until tomorrow.

We built a multi-agent system to solve both, autonomously."

## Slide 2: The Spoof Guard Demo (0:45 - 1:30)
*(Click 'Fake Spoof Attack' on Streamlit UI)*
**Speaker:**
"Our first agent is the Spoof Guard. It runs in under 200 milliseconds. 
If someone flashes a fake Paytm app, the agent instantly checks the gateway hash, detects the anomaly, and pushes a 'FRAUD ALERT' directly to the Merchant's P4B app. 

*(Click '2G Network Lag' on Streamlit UI)*
But what if it's a real payment, and the Soundbox is just buffering on a 2G network? Our agent checks the MQTT telemetry. It sees the gateway cleared it, realizes the Soundbox is just lagging, and pushes a 'Payment Safe, Audio Delayed' notification. We just neutralized merchant anxiety in real-time."

## Slide 3: The LSTM Liquidity Engine (1:30 - 2:30)
*(Click 'Amul Invoice' on Streamlit UI)*
**Speaker:**
"Now for the cash crunch. The merchant gets a WhatsApp bill from Amul for ₹4,500. But the merchant only has ₹1,000 in their account! Worse, they have a ₹3,000 Paytm Loan EMI due tomorrow morning. 

A dumb algorithm would block this payment, forcing the merchant to default on Amul.
But we didn't use a dumb algorithm. We trained a **PyTorch LSTM Neural Network** on 400,000 rows of Kaggle retail data. 

Our Liquidity Engine Agent asks the Neural Network to predict the future. The LSTM looks at the merchant's history and predicts they will easily make ₹8,450 during tonight's evening rush. 
Because the AI guarantees future revenue, our system **auto-approves** the Amul payment instantly, saving the merchant's inventory without risking the loan."

## Slide 4: Production Readiness (2:30 - 3:00)
**Speaker:**
"This isn't just a Python script. 
1. We have a robust **FastAPI backend** handling idempotency and 504 Bank timeouts.
2. We used **Phinite-compliant Maker-Checker guardrails** to redact PII from invoices. 
3. The entire architecture is fully containerized with **Docker**, ready to deploy to AWS today.

We are Paytm Vyapar Saathi. We turn static ledgers into intelligent cashflow engines. Thank you!"
