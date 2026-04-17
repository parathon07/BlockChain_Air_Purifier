"""
Centralized configuration for the blockchain compliance layer.

All settings are loaded from environment variables with sane defaults
for local development and testing.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
#  Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("COMPLIANCE_DB_PATH", str(BASE_DIR / "data" / "blocks.db"))
EVENTS_DB_PATH = os.getenv("COMPLIANCE_EVENTS_DB_PATH", str(BASE_DIR / "data" / "events.db"))

# --------------------------------------------------------------------------- #
#  Batching
# --------------------------------------------------------------------------- #
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
BATCH_TIME_TRIGGER_SECONDS = int(os.getenv("BATCH_TIME_TRIGGER_SECONDS", "86400"))  # 24h

# --------------------------------------------------------------------------- #
#  Ethereum / Web3
# --------------------------------------------------------------------------- #
ETHEREUM_RPC_URL = os.getenv("ETHEREUM_RPC_URL", "http://127.0.0.1:8545")
CONTRACT_ADDRESS = os.getenv("COMPLIANCE_CONTRACT_ADDRESS", "")
PRIVATE_KEY = os.getenv("COMPLIANCE_PRIVATE_KEY", "")

# Path to the compiled contract ABI
CONTRACT_ABI_PATH = os.getenv(
    "COMPLIANCE_CONTRACT_ABI_PATH",
    str(Path(__file__).resolve().parent / "contracts" / "SafetyComplianceAnchor.abi.json"),
)

# --------------------------------------------------------------------------- #
#  Anchoring behaviour
# --------------------------------------------------------------------------- #
ANCHOR_MAX_RETRIES = int(os.getenv("ANCHOR_MAX_RETRIES", "5"))
ANCHOR_INITIAL_BACKOFF_SECONDS = float(os.getenv("ANCHOR_INITIAL_BACKOFF_SECONDS", "1.0"))
ANCHOR_MAX_BACKOFF_SECONDS = float(os.getenv("ANCHOR_MAX_BACKOFF_SECONDS", "300.0"))

# --------------------------------------------------------------------------- #
#  Logging
# --------------------------------------------------------------------------- #
LOG_LEVEL = os.getenv("COMPLIANCE_LOG_LEVEL", "INFO")
