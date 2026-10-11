# Paytm Vyapar Saathi - 3-Minute Hackathon Pitch Script

## Slide 1: The Problem (0:00 - 0:45)
**Speaker:** 
"Hello Judges. We built Paytm Vyapar Saathi on the Phinite OS. We are tackling two critical problems for the everyday Paytm merchant that exist *outside* of the happy path:
1. **The Spoof & Lag Problem:** When a customer pays, but the Soundbox is silent because of a 2G network drop. The merchant panics, thinking it's a Spoof App. 
2. **The 4:00 PM Liquidity Crunch:** The Amul distributor wants ₹4,500 for milk crates. The merchant has ₹6,000 of today's sales unsettled, but ₹3,000 of it must stay for tomorrow morning's loan EMI. Settling everything pays Amul and bounces the EMI.

We built a multi-agent system to solve both, autonomously."

## Slide 2: The Spoof Guard Demo (0:45 - 1:30)
*(Click 'Fake Spoof Attack' on Streamlit UI)*
**Speaker:**
"Our first agent is the Spoof Guard, built for a 600 millisecond budget.
If someone flashes a fake Paytm app, shows an old receipt, or edits the amount on a real one, the agent checks the gateway record, the merchant it was paid to, its time and its amount, and pushes a 'FRAUD ALERT' to the merchant's P4B app.

*(Click '2G Network Lag' on Streamlit UI)*
But what if it's a real payment, and the Soundbox is just buffering on a 2G network? Our agent checks the MQTT telemetry. It sees the gateway cleared it, realizes the Soundbox is just lagging, and pushes a 'Payment Safe, Audio Delayed' notification. We just neutralized merchant anxiety in real-time."

## Slide 3: The EMI-Safe Liquidity Engine (1:30 - 2:30)
*(Choose 'Supplier bill at 16:00' and click 'Process bill' in the Streamlit UI)*
**Speaker:**
"Now the cash crunch. Amul sends a WhatsApp bill for ₹4,500. Our Supplier Ledger agent masks the bank details, reads the amount from the message and checks that it really appears there.

The merchant has ₹6,000 unsettled, and ₹3,000 must stay for tomorrow's EMI, so only ₹3,000 can be paid safely right now.

Our Liquidity Engine asks a PyTorch LSTM to forecast tonight's sales from the merchant's last three days. We never trust the raw forecast: we use a conservative floor that actual sales beat on about 89% of held-out days. Because the ₹1,500 gap fits under that floor and under the advance limit, the merchant gets ₹3,000 settled now plus a ₹1,500 advance repaid from tonight's sales. The EMI is still fully covered, and an independent check re-derives the plan before anything is paid. If the forecast could not cover the gap, the merchant would be told to pay ₹3,000 now and defer the rest."

## Slide 4: Production Readiness (2:30 - 3:00)
**Speaker:**
"This isn't just a Python script. 
1. Every payout is **signed**, carries an **idempotency key**, and after a bank 504 we check the order status instead of paying twice.
2. **Maker-checker guardrails**: PII is masked before any model sees it, and every payment plan is re-checked independently.
3. An automated test suite covers every guardrail, and the whole system is containerised with **Docker**.

We are Paytm Vyapar Saathi. We turn static ledgers into intelligent cashflow engines. Thank you!"
