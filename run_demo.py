"""
Paytm Vyapar Saathi: 3-Minute Winning Hackathon Demo Runner
Phinite x Paytm Track 2: AI for Small Businesses
Walks through:
1. Malicious Spoof Detection vs. 2G MQTT Lag Resolution (Sub-600ms)
2. WhatsApp FMCG Invoice Parsing & Deterministic EMI Protection
3. Native P4B Deep Link Execution, 504 Timeout Recovery, and Phinite Observability
"""

import asyncio
import os
import sys
import time
import httpx
from colorama import Fore, Style, init

import config
from mock_backend.sandbox_client import create_payment

# Fix Windows console encoding for Unicode/ANSI
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Enable ANSI colors
init(autoreset=True)

BACKEND_URL = config.BACKEND_URL
DEVICE_IMEI = "864201938472910"

def sla_label(result: dict) -> str:
    return f"{Fore.GREEN}MET" if result.get("sla_met") else f"{Fore.RED}MISSED"

def print_header(title: str):
    print("\n" + "=" * 78)
    print(f"{Fore.CYAN}{Style.BRIGHT}{title.center(78)}")
    print("=" * 78)

def print_step(step_num: str, title: str):
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}>> [{step_num}] {title}")
    print("-" * 78)

async def check_backend_alive():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{BACKEND_URL}/docs")
            return resp.status_code == 200
    except Exception:
        return False

async def main():
    print_header("PAYTM VYAPAR SAATHI: PHINITE MULTI-AGENT SYSTEM")
    print(f"{Fore.WHITE}Autonomous Soundbox Anti-Fraud & Working-Capital Liquidity Balancer")
    print(f"{Fore.GREEN}Platform: Phinite Enterprise Agentic OS  |  Track: Paytm Track 2 (SMBs)\n")

    # Verify Mock Backend
    is_alive = await check_backend_alive()
    if not is_alive:
        print(f"{Fore.RED}[ERROR] Backend is not running at {BACKEND_URL}!")
        print(f"{Fore.YELLOW}Please start it using: uvicorn mock_backend.main:app --port 8000")
        sys.exit(1)

    print(f"{Fore.GREEN}[OK] Connected to Paytm Mock Gateway & Phinite Telemetry Switch.")
    time.sleep(1)

    from agents.supervisor import MasterSupervisorAgent

    supervisor = MasterSupervisorAgent(backend_url=BACKEND_URL)

    # =========================================================================
    # MINUTE 0:00 - 1:00: THE SPOOF VS. 2G CELLULAR LAG DILEMMA
    # =========================================================================
    print_header("MINUTE 0:00 - 1:00: THE SPOOF VS. 2G MQTT LAG DILEMMA")

    # Scenario 1A: Malicious Spoof App Attack
    print_step("SCENARIO 1A", "Counterfeit Paytm Spoof App Attack")
    print(f"{Fore.WHITE}Customer flashes counterfeit app showing: 'Paid Rs. 500 to Sharma General Store'")
    print(f"{Fore.MAGENTA}Querying Spoof Guard Agent with fake transaction 'TXN_FAKE_SPOOF_778'...")

    t0 = time.time()
    fake_result = await supervisor.handle_soundbox_event(
        txn_id="TXN_FAKE_SPOOF_778",
        device_imei=DEVICE_IMEI
    )
    t_fake_ms = int((time.time() - t0) * 1000)

    print(f"  * Latency: {Fore.CYAN}{t_fake_ms}ms {Fore.WHITE}(SLA budget 600ms: {sla_label(fake_result)}{Fore.WHITE})")
    print(f"  * Gateway Hash Match: {Fore.RED}{fake_result['gateway_hash_matched']}")
    print(f"  * Decision: {Fore.RED}{Style.BRIGHT}{fake_result['status']}")
    print(f"  * Message: {Fore.YELLOW}{fake_result['message']}")
    print(f"  * P4B Trigger: {Fore.RED}Broadcasted {fake_result['p4b_action_triggered']} to Merchant App Screen")
    assert fake_result["status"] == "SPOOF_DETECTED", "Expected spoof detection!"
    time.sleep(1)

    # Scenario 1B: Legitimate Payment suffering 2G MQTT Cellular Latency
    print_step("SCENARIO 1B", "Legitimate Payment with 2G Cellular MQTT Drop")
    payment = await create_payment(50.00, DEVICE_IMEI, mqtt_delivered=False, backend_url=BACKEND_URL)
    print(f"{Fore.WHITE}Customer pays Rs. 50.00 ({payment['txn_id']}). Gateway cleared, but Soundbox is silent.")
    print(f"{Fore.MAGENTA}2G network dropped MQTT QoS 1 PUBACK packet. Soundbox buffering...")
    print(f"{Fore.WHITE}Spoof Guard Agent inspecting broker telemetry and gateway switch...")

    t1 = time.time()
    legit_result = await supervisor.handle_soundbox_event(
        txn_id=payment["txn_id"],
        device_imei=DEVICE_IMEI,
        claimed_amount=50.00
    )
    t_legit_ms = int((time.time() - t1) * 1000)

    print(f"  * Latency: {Fore.CYAN}{t_legit_ms}ms {Fore.WHITE}(SLA budget 600ms: {sla_label(legit_result)}{Fore.WHITE})")
    print(f"  * Gateway Hash Match: {Fore.GREEN}{legit_result['gateway_hash_matched']}")
    print(f"  * MQTT PUBLISH Detected: {Fore.GREEN}{legit_result['mqtt_publish_detected']}")
    print(f"  * Soundbox PUBACK Received: {Fore.YELLOW}{legit_result['puback_received']} (Buffering over 2G)")
    print(f"  * Decision: {Fore.CYAN}{Style.BRIGHT}{legit_result['status']}")
    print(f"  * P4B Card: {Fore.GREEN}Pushed '{legit_result['p4b_action_triggered']}' to merchant app:")
    print(f"    \"{Fore.WHITE}Payment of Rs. 50 Received. Soundbox audio delayed due to network.{Fore.GREEN}\"")
    print(f"  {Fore.GREEN}[OK] Neutralized merchant anxiety in real time; customer allowed to leave safely.")
    assert legit_result["status"] == "AUDIO_DELAYED", "Expected AUDIO_DELAYED!"
    time.sleep(1)

    # Scenario 1C: the same genuine receipt re-used to claim a bigger amount
    print_step("SCENARIO 1C", "Real Receipt, Tampered Amount (Replay Attack)")
    print(f"{Fore.WHITE}Fraudster shows the genuine Rs. 50 receipt edited to read Rs. 500.")
    replay_result = await supervisor.handle_soundbox_event(
        txn_id=payment["txn_id"],
        device_imei=DEVICE_IMEI,
        claimed_amount=500.00
    )
    print(f"  * Decision: {Fore.RED}{Style.BRIGHT}{replay_result['status']}")
    print(f"  * Reason: {Fore.YELLOW}{replay_result['message']}")
    assert replay_result["status"] == "SPOOF_DETECTED", "Expected the tampered amount to be caught!"
    time.sleep(1)

    # =========================================================================
    # MINUTE 1:00 - 2:00: THE 16:00 FMCG LIQUIDITY CRUNCH
    # =========================================================================
    print_header("MINUTE 1:00 - 2:00: THE 16:00 FMCG DISTRIBUTOR CASH CRUNCH")
    print_step("SCENARIO 2A", "Unstructured WhatsApp Invoice Ingestion & PII Redaction")

    raw_whatsapp_bill = (
        "From: Amul Distributor Depot #4\n"
        "Delivery Note #INV-8891\n"
        "5 Crates Amul Taaza + 10 Dahi Tubs.\n"
        "Total Amount Due: Rs 4500.00. Payment required strictly by 16:00 today.\n"
        "Payee VPA: amul.dist@paytm | Bank Acc: 98127391823719 | IFSC: PYTM0123456"
    )
    print(f"{Fore.WHITE}Incoming WhatsApp Message:\n{Fore.BLUE}{raw_whatsapp_bill}\n")

    # The supervisor routes the bill: Supplier Ledger (PII redaction + extraction) -> Liquidity Engine
    print(f"{Fore.MAGENTA}Supervisor routing the bill: Supplier Ledger Agent -> Liquidity Engine Agent...")
    outcome = await supervisor.handle_event({
        "type": "supplier_bill",
        "raw_message": raw_whatsapp_bill,
        "vendor_id": "amul_distributor_vpa"
    })
    parsed_invoice, sim_result = outcome["bill"], outcome["plan"]
    print(f"{Fore.GREEN}[OK] PII redacted before the text left the agent: {parsed_invoice['pii_sanitized_at_ingress']}")
    print(f"  * Text sent onward:\n{Fore.LIGHTBLACK_EX}{parsed_invoice['sanitized_text']}\n")
    print(f"  * Vendor: {Fore.WHITE}{parsed_invoice['vendor_name']} ({parsed_invoice['invoice_number']})")
    print(f"  * Extracted Due Amount: {Fore.GREEN}Rs. {parsed_invoice['due_amount']:,.2f} (checked against the message text)")
    print(f"  * Payment Cutoff: {Fore.WHITE}{parsed_invoice['cutoff_time']}")
    items = ", ".join(f"{i['quantity']} x {i['item']}" for i in parsed_invoice["line_items"])
    print(f"  * Line Items: {Fore.WHITE}{items or 'none listed'}")

    print_step("SCENARIO 2B", "EMI-Safe Payment Plan (Ledger + PyTorch LSTM Floor)")
    async with httpx.AsyncClient() as client:
        state = (await client.get(f"{BACKEND_URL}/api/v1/merchant/state/{config.DEMO_MERCHANT_ID}")).json()
    print(f"{Fore.WHITE}Unsettled balance at 16:00 (ledger):    {Fore.CYAN}Rs. {state['current_unsettled_balance']:,.2f}")
    print(f"{Fore.WHITE}Tomorrow 05:00 AM automated loan EMI:   {Fore.YELLOW}Rs. {state['daily_loan_emi']:,.2f}")
    print(f"{Fore.WHITE}Bill to pay:                            {Fore.CYAN}Rs. {parsed_invoice['due_amount']:,.2f}")
    print(f"{Fore.RED}A full on-demand sweep would leave Rs. 0 and bounce tomorrow's EMI.")

    print(f"\n{Fore.MAGENTA}Worker 3 (Liquidity Engine) plan:")
    print(f"  * Safe to settle now (balance - EMI): {Fore.GREEN}Rs. {sim_result['safe_settlement_limit']:,.2f}")
    print(f"  * LSTM forecast of tonight's sales:   {Fore.WHITE}Rs. {sim_result['evening_forecast_expected']:,.2f} expected, "
          f"Rs. {sim_result['evening_forecast_floor']:,.2f} conservative floor")
    print(f"  * Decision: {Fore.GREEN}{Style.BRIGHT}{sim_result['decision']}")
    print(f"  * Settle now: {Fore.GREEN}Rs. {sim_result['recommended_micro_settlement']:,.2f}"
          f"{Fore.WHITE} | Advance: Rs. {sim_result['advance_amount']:,.2f} | Unpaid: Rs. {sim_result['unpaid_amount']:,.2f}")
    print(f"  * Balance left for the EMI batch: {Fore.YELLOW}Rs. {sim_result['projected_eod_balance']:,.2f}")
    check = sim_result["maker_checker_verification"]
    print(f"  * Independent maker-checker: {Fore.GREEN if check['passed'] else Fore.RED}{'PASSED' if check['passed'] else check['violations']}")
    assert check["passed"], "Maker-checker rejected the plan!"
    assert sim_result["projected_eod_balance"] >= sim_result["daily_loan_emi"], "EMI reserve breached!"
    time.sleep(1)

    # =========================================================================
    # MINUTE 2:00 - 3:00: NATIVE EXECUTION & OBSERVABILITY
    # =========================================================================
    print_header("MINUTE 2:00 - 3:00: NATIVE EXECUTION & ABSOLUTE SAFETY")
    print_step("SCENARIO 3A", "Paytm for Business (P4B) Deep-Link Notification")

    print(f"{Fore.WHITE}Outbound Notification Dispatched to Merchant Mobile:")
    print(f"  * Title: {Fore.CYAN}{sim_result['p4b_notification_payload']['title']}")
    print(f"  * Body:  {Fore.WHITE}{sim_result['p4b_notification_payload']['body']}")
    print(f"  * Native Deep Link URI: {Fore.BLUE}{sim_result['action_deep_link']}")
    print(f"  {Fore.GREEN}[OK] Merchant taps the notification to approve the Rs. {sim_result['recommended_micro_settlement']:,.2f} settlement.\n")

    # Step: 504 Timeout Simulation & Idempotent Recovery
    print_step("SCENARIO 3B", "Handling a Bank Switch 504 Timeout Without Double Debit")
    print(f"{Fore.MAGENTA}Merchant taps settle. Upstream Bank CBS times out (504)...")
    print(f"{Fore.WHITE}Supervisor does not retry blindly; it checks the order status first...")

    udir_recovery = await supervisor.execute_settlement(
        merchant_id=config.DEMO_MERCHANT_ID,
        required_amount=sim_result["recommended_micro_settlement"],
        routing_rail="IMPS",
        simulate_504=True
    )
    retry = await supervisor.execute_settlement(
        merchant_id=config.DEMO_MERCHANT_ID,
        required_amount=sim_result["recommended_micro_settlement"],
        routing_rail="IMPS",
        order_id=udir_recovery["request"]["body"]["orderId"],
        simulate_504=True
    )
    print(f"  * NPCI UDIR Code: {Fore.GREEN}{udir_recovery['request']['body']['udir_reconciliation_code']} (Beneficiary Credited Post-Timeout)")
    print(f"  * UTR Number: {Fore.WHITE}{udir_recovery['request']['body']['utrNo']}")
    print(f"  * Status: {Fore.GREEN}{Style.BRIGHT}{udir_recovery['request']['body']['status']}")
    print(f"  * Retry of the same order returned the original payout: {Fore.GREEN}no double debit")
    assert retry["request"]["body"]["transactionId"] == udir_recovery["request"]["body"]["transactionId"]
    time.sleep(1)

    # Step: Observability
    print_step("EVALUATION", "Observability Dashboard")
    async with httpx.AsyncClient() as client:
        obs_resp = await client.get(f"{BACKEND_URL}/api/v1/observability/metrics")
        obs_data = obs_resp.json()

    metrics = obs_data["metrics"]
    print(f"{Fore.WHITE}Real-Time Platform Governance Summary:")
    print(f"  * Telemetry Verifications:         {Fore.CYAN}{metrics['telemetry_verifications']}")
    print(f"  * Spoof Attacks Neutralized:        {Fore.GREEN}{metrics['spoof_attacks_neutralized']}")
    print(f"  * 2G Audio Lag Calming Alerts:      {Fore.GREEN}{metrics['audio_delayed_calming_alerts']}")
    print(f"  * EMI Breaches Prevented:           {Fore.GREEN}{metrics['emi_breaches_prevented']}")
    print(f"  * Total Capital Settled:            {Fore.GREEN}Rs. {metrics['total_capital_settled_inr']:,.2f}")
    print(f"  * Average Spoof Guard Latency:      {Fore.CYAN}{metrics['avg_spoof_guard_latency_ms']}ms ({metrics['latency_sla_compliance']})")
    print(f"  * p95 Spoof Guard Latency:          {Fore.CYAN}{metrics['p95_spoof_guard_latency_ms']}ms")
    print(f"  * PII Reaching Backend Unredacted:  {Fore.GREEN}{metrics['pii_leakage_events']}")

    print("\n" + "=" * 78)
    print(f"{Fore.GREEN}{Style.BRIGHT}{'*** ALL 3-MINUTE HACKATHON DEMO ASSERTIONS PASSED! ***'.center(78)}")
    print("=" * 78 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
