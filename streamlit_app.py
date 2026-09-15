import streamlit as st
import time

st.set_page_config(page_title="Phinite OS | Paytm Vyapar Saathi", layout="wide")

# Enterprise CSS Styling (No Emojis, Clean B2B Look)
st.markdown("""
    <style>
    .metric-container {
        border: 1px solid #333;
        border-radius: 5px;
        padding: 15px;
        background-color: #121212;
        margin-bottom: 20px;
    }
    .log-window {
        background-color: #0d1117;
        color: #58a6ff;
        padding: 20px;
        font-family: 'Courier New', Courier, monospace;
        border-radius: 5px;
        border: 1px solid #30363d;
        height: 550px;
        overflow-y: scroll;
        white-space: pre-wrap;
        line-height: 1.6;
    }
    .system-header {
        border-bottom: 2px solid #00baf2;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }
    .p4b-device {
        border: 2px solid #444;
        border-radius: 15px;
        padding: 25px;
        background-color: #0a0a0a;
        min-height: 550px;
    }
    .tag {
        background-color: #00baf2;
        color: black;
        padding: 3px 8px;
        border-radius: 3px;
        font-size: 0.8em;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="system-header"><h1>Phinite Orchestration: Paytm Vyapar Saathi Node</h1><p>Track 2: AI for SMBs | Architecture: Autonomous Multi-Agent OS</p></div>', unsafe_allow_html=True)

# Sidebar controls
st.sidebar.markdown("### Execution Triggers")
scenario = st.sidebar.radio("Select System State:", [
    "1. System Idle",
    "2. Anomaly: Spoof App Detection",
    "3. Anomaly: 2G Network Latency",
    "4. AI Routine: LSTM Liquidity Allocation"
])

# Layout
col1, col2 = st.columns([1, 1.4])

with col1:
    st.markdown("### Client View: Paytm for Business (P4B)")
    
    # Use native Streamlit container with a border instead of raw HTML
    with st.container(border=True):
        st.markdown("#### 🏪 Sharma General Store")
        st.divider()
        
        m1, m2 = st.columns(2)
        m1.metric("Unsettled T+1 Balance", "₹1,000.00")
        m2.metric("Pending Loan EMI (T+1)", "₹3,000.00")
        
        st.write("") # spacing
        
        if scenario == "2. Anomaly: Spoof App Detection":
            st.error("**SYSTEM ALERT: FRAUD INTERCEPTED**\n\nCounterfeit spoof attempt detected via gateway telemetry. No valid transaction hash present. Do not release goods.")
        elif scenario == "3. Anomaly: 2G Network Latency":
            st.warning("**STATUS: AUDIO DELAYED (2G CONGESTION)**\n\nPayment of ₹50.00 successfully cleared Gateway. Soundbox audio delivery delayed. Payment is mathematically secure.")
        elif scenario == "4. AI Routine: LSTM Liquidity Allocation":
            st.info("**INVOICE DETECTED: Amul Distributor**\n\nLiability: ₹4,500.00 | Deadline: 16:00 IST")
            st.success("**LIQUIDITY ENGINE: SETTLEMENT APPROVED**\n\nDeep Learning (LSTM) predicts sufficient evening revenue to cover tomorrow's EMI. Safe to execute payout.")
            if st.button("EXECUTE SETTLEMENT", use_container_width=True):
                st.success("Transaction executed successfully. Double-debit protection active.")

with col2:
    st.markdown("### Backend View: Agent Observability Trace")
    
    log_text = ""
    if scenario == "1. System Idle":
        log_text = "[SYSTEM] Initializing Phinite OS Environment...\n"
        log_text += "[SYSTEM] Connected to Paytm Mock Gateway.\n"
        log_text += "[SYSTEM] Awaiting MQTT Broker Telemetry & Webhooks...\n"
        
    elif scenario == "2. Anomaly: Spoof App Detection":
        log_text = "[Worker 1: Spoof Guard Agent] Invoked on target: 'TXN_FAKE_SPOOF_778'\n"
        log_text += "--------------------------------------------------------\n"
        log_text += "[TRACE] Computing cross-reference with Gateway Switch...\n"
        log_text += "[TRACE] Execution Latency: 174ms (SLA Budget: <600ms) [PASSED]\n"
        log_text += "[TRACE] Gateway Hash Match: FALSE\n"
        log_text += "[DECISION] Output: SPOOF_DETECTED\n"
        log_text += "[ACTION] Broadcasting FRAUD_ALERT to P4B Client Socket...\n"
        
    elif scenario == "3. Anomaly: 2G Network Latency":
        log_text = "[Worker 1: Spoof Guard Agent] Invoked on target: 'TXN_9876543210'\n"
        log_text += "--------------------------------------------------------\n"
        log_text += "[TRACE] Computing cross-reference with Gateway Switch...\n"
        log_text += "[TRACE] Execution Latency: 177ms (SLA Budget: <600ms) [PASSED]\n"
        log_text += "[TRACE] Gateway Hash Match: TRUE\n"
        log_text += "[TRACE] Soundbox PUBACK Received: FALSE (Queue buffered)\n"
        log_text += "[DECISION] Output: AUDIO_DELAYED\n"
        log_text += "[ACTION] Pushing asynchronous confirmation to P4B Client...\n"
        
    elif scenario == "4. AI Routine: LSTM Liquidity Allocation":
        log_text = "[Worker 2: Supplier Ledger Agent] Processing unstructured input...\n"
        log_text += "--------------------------------------------------------\n"
        log_text += "[GUARDRAIL] PII Sanitization Active.\n"
        log_text += "[TRACE] Masked Data: [REDACTED_BANK_ACC], [REDACTED_IFSC]\n"
        log_text += "[TRACE] Extracted Liability: ₹4,500.00\n\n"
        
        log_text += "[Worker 3: Liquidity Engine Agent] Evaluating dynamic cashflow...\n"
        log_text += "--------------------------------------------------------\n"
        log_text += "[TRACE] Loading PyTorch LSTM Weights (models/lstm_model.pth)...\n"
        log_text += "[TRACE] Tensor Input: (Day-3, Day-2, Day-1, Today) Velocity\n"
        log_text += "[INFERENCE] Predicted Evening Revenue: ₹8,450.00\n"
        log_text += "[ASSERTION] Evaluate: 4500 (Req) + 3000 (EMI) <= 1000 (Bal) + 8450 (Proj)\n"
        log_text += "[DECISION] Output: TRUE (Micro-loan backed by future earnings)\n"
        log_text += "[ACTION] Authorizing settlement to Amul Distributor...\n"
        
    st.markdown(f'<div class="log-window">{log_text}</div>', unsafe_allow_html=True)
