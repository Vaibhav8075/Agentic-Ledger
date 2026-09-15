
import uvicorn
import threading
import time
import httpx

def run_server():
    uvicorn.run('mock_backend.main:app', host='127.0.0.1', port=8001, log_level='error')

t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(3)
resp = httpx.post('http://127.0.0.1:8001/api/v1/liquidity/simulate', json={'current_unsettled_balance': 1000.0, 'due_amount': 4500.0, 'cutoff_time': '2026-09-10T16:00:00+05:30'})
print('Status:', resp.status_code)

