"""
Paytm Vyapar Saathi: live Paytm for Business (P4B) simulation.
Every button calls the same agents as run_demo.py against the running backend; nothing is scripted.

Start the backend first:  python -m uvicorn mock_backend.main:app --port 8000
Then:                     streamlit run streamlit_app.py
"""

import asyncio

import httpx
import streamlit as st

import config
from agents.supervisor import MasterSupervisorAgent
from mock_backend.sandbox_client import create_payment

MID = config.DEMO_MERCHANT_ID
DEVICE_IMEI = "864201938472910"
DEFAULT_BILL = (
    "From: Amul Distributor Depot #4\n"
    "Delivery Note #INV-8891\n"
    "5 Crates Amul Taaza + 10 Dahi Tubs.\n"
    "Total Amount Due: Rs 4500.00. Payment required strictly by 16:00 today.\n"
    "Payee VPA: amul.dist@paytm | Bank Acc: 98127391823719 | IFSC: PYTM0123456"
)
NOTIFICATION_STYLE = {
    "FRAUD_ALERT_SPOOF_ATTEMPT": st.error,
    "AUDIO_DELAYED_CONFIRMATION": st.warning,
    "LIQUIDITY_OPTIMIZATION_PROMPT": st.info,
}

st.set_page_config(page_title="Vyapar Saathi | Live Demo", layout="wide")
st.session_state.setdefault("supervisor", MasterSupervisorAgent(config.BACKEND_URL))
st.session_state.setdefault("trace", [])
st.session_state.setdefault("bill_outcome", None)
supervisor: MasterSupervisorAgent = st.session_state.supervisor


def backend(method: str, path: str) -> dict:
    with httpx.Client(base_url=config.BACKEND_URL, timeout=5.0) as client:
        resp = client.request(method, path)
        resp.raise_for_status()
        return resp.json()


def act(title: str, coro) -> None:
    """Runs one agent action, records the real response (or error) in the trace, then refreshes."""
    try:
        result = asyncio.run(coro)
    except httpx.HTTPStatusError as exc:
        result = {"error": exc.response.status_code, "detail": exc.response.json().get("detail")}
    except (httpx.HTTPError, ValueError) as exc:
        result = {"error": type(exc).__name__, "detail": str(exc)}
    st.session_state.trace.insert(0, {"title": title, "result": result})
    if title.startswith("Supplier bill") and "error" not in result:
        st.session_state.bill_outcome = result
    st.rerun()


async def claim(amount_paid, amount_claimed, delivered=False, txn_id=None):
    if txn_id is None:
        payment = await create_payment(amount_paid, DEVICE_IMEI, delivered, backend_url=config.BACKEND_URL)
        txn_id = payment["txn_id"]
    return await supervisor.handle_event({"type": "payment_claim", "txn_id": txn_id,
                                          "device_imei": DEVICE_IMEI, "claimed_amount": amount_claimed})


st.title("Paytm Vyapar Saathi")
st.caption(f"Live sandbox at {config.BACKEND_URL}. Every panel shows real responses from the agents.")

try:
    state = backend("GET", f"/api/v1/merchant/state/{MID}")
except httpx.HTTPError:
    st.error(f"Backend not reachable at {config.BACKEND_URL}. Start it with "
             "`python -m uvicorn mock_backend.main:app --port 8000` and reload.")
    st.stop()

scenario = st.sidebar.radio("Scenario", ["Payment claim at the counter", "Supplier bill at 16:00"])
if st.sidebar.button("Reset sandbox"):
    backend("POST", "/api/v1/sandbox/reset")
    st.session_state.trace, st.session_state.bill_outcome = [], None
    supervisor.audit_trail.clear()
    st.rerun()

app_col, agent_col = st.columns([1, 1.4])

with app_col:
    st.subheader(f"P4B app: {state['merchant_name']}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Unsettled balance", f"₹{state['current_unsettled_balance']:,.2f}")
    m2.metric("EMI reserve (05:00)", f"₹{state['daily_loan_emi']:,.2f}")
    m3.metric("Settled today", f"₹{state['settled_today']:,.2f}")
    st.markdown("**Notifications**")
    notes = backend("GET", f"/api/v1/p4b/notifications/{MID}")["notifications"]
    for note in reversed(notes[-5:]):
        NOTIFICATION_STYLE.get(note["notification_type"], st.info)(f"**{note['title']}**\n\n{note['body']}")
    if not notes:
        st.write("No notifications yet.")

with agent_col:
    if scenario == "Payment claim at the counter":
        st.subheader("Is this payment real?")
        c1, c2, c3 = st.columns(3)
        if c1.button("Fake app screen (₹500)", use_container_width=True):
            act("Payment claim: fake app", claim(None, 500.0, txn_id="TXN_FAKE_SPOOF_778"))
        if c2.button("Real ₹50, Soundbox silent", use_container_width=True):
            act("Payment claim: real payment, 2G lag", claim(50.0, 50.0))
        if c3.button("Real ₹50 receipt edited to ₹500", use_container_width=True):
            act("Payment claim: tampered amount", claim(50.0, 500.0))
    else:
        st.subheader("Supplier bill on WhatsApp")
        bill_text = st.text_area("Message", DEFAULT_BILL, height=130)
        if st.button("Process bill", type="primary"):
            act("Supplier bill", supervisor.handle_event({"type": "supplier_bill", "raw_message": bill_text,
                                                          "vendor_id": "amul_distributor_vpa"}))
        outcome = st.session_state.bill_outcome
        if outcome:
            plan, bill = outcome["plan"], outcome["bill"]
            st.markdown(f"**{bill['vendor_name']}** asks for **₹{bill['due_amount']:,.2f}**"
                        f" by {bill['cutoff_time'] or 'no stated time'}")
            p1, p2, p3 = st.columns(3)
            p1.metric("Settle now", f"₹{plan['recommended_micro_settlement']:,.2f}")
            p2.metric("Advance", f"₹{plan['advance_amount']:,.2f}")
            p3.metric("Left unpaid", f"₹{plan['unpaid_amount']:,.2f}")
            check = plan["maker_checker_verification"]
            st.write(f"Decision: `{plan['decision']}` · forecast of tonight's sales ₹{plan['evening_forecast_expected']:,.2f}"
                     f" (floor ₹{plan['evening_forecast_floor']:,.2f}) · maker-checker "
                     f"{'passed' if check['passed'] else 'FAILED: ' + '; '.join(check['violations'])}")
            simulate_504 = st.checkbox("Simulate a bank timeout (504)")
            amount = plan["recommended_micro_settlement"]
            if st.button(f"Approve: settle ₹{amount:,.2f}", disabled=amount <= 0 or not check["passed"]):
                act("Settlement", supervisor.handle_event({"type": "settlement_tap", "amount": amount,
                                                           "simulate_504": simulate_504}))

    st.subheader("Agent trace")
    for i, item in enumerate(st.session_state.trace[:6]):
        with st.expander(item["title"], expanded=i == 0):
            st.json(item["result"])
    if supervisor.audit_trail:
        st.markdown("**Supervisor audit trail**")
        st.table(list(reversed(supervisor.audit_trail[-8:])))
