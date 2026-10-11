"""
Runtime settings shared by the agents, the mock backend and the UI.
Every value can be overridden with an environment variable (see .env.example).
"""

import os

BACKEND_URL = os.getenv("VS_BACKEND_URL", "http://127.0.0.1:8000")
DEMO_MERCHANT_ID = os.getenv("VS_MERCHANT_ID", "HelloM8xxxxxxxx45")

# Signing key shared by the agents and the mock gateway. The default only works against the
# local sandbox; a real deployment must inject its own key from a secret store.
MERCHANT_SIGNING_KEY = os.getenv("VS_MERCHANT_SIGNING_KEY", "sandbox-signing-key-not-secret")
