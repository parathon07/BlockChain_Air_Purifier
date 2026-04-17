"""
Ethereum Anchor Module.

Python client for submitting Merkle roots to the SafetyComplianceAnchor
smart contract and querying on-chain anchor records.

Falls back gracefully when Ethereum is unavailable — the safety system
is never blocked by blockchain operations.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from . import config

logger = logging.getLogger(__name__)


@dataclass
class AnchorResult:
    """Result of an anchoring operation."""
    success: bool
    batch_id: Optional[int] = None
    tx_hash: Optional[str] = None
    merkle_root: Optional[str] = None
    error: Optional[str] = None


@dataclass
class AnchorRecord:
    """On-chain anchor record retrieved from the smart contract."""
    merkle_root: str
    timestamp: int
    batch_id: int


class EthereumAnchor:
    """
    Client for the SafetyComplianceAnchor Ethereum smart contract.

    Handles:
    - Submitting Merkle roots (write transactions)
    - Querying anchor records (read calls)
    - Verifying roots on-chain (read calls)
    - Retry logic with exponential backoff
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        contract_address: Optional[str] = None,
        contract_abi_path: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> None:
        self.rpc_url = rpc_url or config.ETHEREUM_RPC_URL
        self.contract_address = contract_address or config.CONTRACT_ADDRESS
        self.private_key = private_key or config.PRIVATE_KEY
        self.abi_path = contract_abi_path or config.CONTRACT_ABI_PATH

        self._web3 = None
        self._contract = None
        self._account = None

        self._connected = False

    # ------------------------------------------------------------------ #
    #  Connection
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        """
        Attempt to connect to the Ethereum node and load the contract.

        Returns True if successful, False otherwise.
        """
        try:
            from web3 import Web3

            self._web3 = Web3(Web3.HTTPProvider(self.rpc_url))

            if not self._web3.is_connected():
                logger.warning("Web3 not connected to %s", self.rpc_url)
                self._connected = False
                return False

            # Load ABI
            abi = self._load_abi()

            # Load contract
            self._contract = self._web3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=abi,
            )

            # Load account from private key
            if self.private_key:
                self._account = self._web3.eth.account.from_key(self.private_key)

            self._connected = True
            logger.info("Connected to Ethereum at %s", self.rpc_url)
            return True

        except Exception as e:
            logger.warning("Failed to connect to Ethereum: %s", e)
            self._connected = False
            return False

    def _load_abi(self) -> list:
        """Load the contract ABI from disk."""
        abi_file = Path(self.abi_path)
        if not abi_file.exists():
            raise FileNotFoundError(f"Contract ABI not found: {self.abi_path}")
        return json.loads(abi_file.read_text(encoding="utf-8"))

    @property
    def is_connected(self) -> bool:
        return self._connected and self._web3 is not None and self._web3.is_connected()

    # ------------------------------------------------------------------ #
    #  Write operations
    # ------------------------------------------------------------------ #

    def submit_anchor(self, merkle_root: str) -> AnchorResult:
        """
        Submit a Merkle root to the smart contract.

        Parameters
        ----------
        merkle_root : str
            64-character hex digest (SHA-256 Merkle root).

        Returns
        -------
        AnchorResult
            Contains success status, batch_id, and transaction hash.
        """
        if not self.is_connected:
            if not self.connect():
                return AnchorResult(
                    success=False,
                    error="Not connected to Ethereum",
                    merkle_root=merkle_root,
                )

        root_bytes = bytes.fromhex(merkle_root)

        retries = config.ANCHOR_MAX_RETRIES
        backoff = config.ANCHOR_INITIAL_BACKOFF_SECONDS

        for attempt in range(1, retries + 1):
            try:
                # Build transaction
                nonce = self._web3.eth.get_transaction_count(self._account.address)
                tx = self._contract.functions.submitAnchor(root_bytes).build_transaction({
                    "from": self._account.address,
                    "nonce": nonce,
                    "gas": 100_000,
                    "gasPrice": self._web3.eth.gas_price,
                })

                # Sign and send
                signed = self._web3.eth.account.sign_transaction(tx, self.private_key)
                tx_hash = self._web3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

                # Extract batch_id from event logs
                batch_id = self._extract_batch_id(receipt)

                logger.info(
                    "Anchor submitted: batch_id=%s tx=%s",
                    batch_id, tx_hash.hex(),
                )
                return AnchorResult(
                    success=True,
                    batch_id=batch_id,
                    tx_hash=tx_hash.hex(),
                    merkle_root=merkle_root,
                )

            except Exception as e:
                logger.warning(
                    "Anchor attempt %d/%d failed: %s", attempt, retries, e
                )
                if attempt < retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, config.ANCHOR_MAX_BACKOFF_SECONDS)
                else:
                    return AnchorResult(
                        success=False,
                        error=str(e),
                        merkle_root=merkle_root,
                    )

    def _extract_batch_id(self, receipt: Dict) -> Optional[int]:
        """Extract batch_id from AnchorSubmitted event logs."""
        try:
            logs = self._contract.events.AnchorSubmitted().process_receipt(receipt)
            if logs:
                return logs[0]["args"]["batchId"]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    #  Read operations
    # ------------------------------------------------------------------ #

    def get_anchor(self, batch_id: int) -> Optional[AnchorRecord]:
        """
        Query an anchor record by batch ID.

        Returns None if Ethereum is unavailable.
        """
        if not self.is_connected:
            if not self.connect():
                return None
        try:
            root, ts, bid = self._contract.functions.getAnchor(batch_id).call()
            return AnchorRecord(
                merkle_root=root.hex(),
                timestamp=ts,
                batch_id=bid,
            )
        except Exception as e:
            logger.warning("Failed to get anchor %d: %s", batch_id, e)
            return None

    def verify_root(self, batch_id: int, expected_root: str) -> Optional[bool]:
        """
        Verify a Merkle root against the on-chain record.

        Returns None if Ethereum is unavailable.
        """
        if not self.is_connected:
            if not self.connect():
                return None
        try:
            root_bytes = bytes.fromhex(expected_root)
            return self._contract.functions.verifyRoot(batch_id, root_bytes).call()
        except Exception as e:
            logger.warning("Failed to verify root for batch %d: %s", batch_id, e)
            return None

    def get_anchor_count(self) -> Optional[int]:
        """Return total number of anchors on-chain."""
        if not self.is_connected:
            if not self.connect():
                return None
        try:
            return self._contract.functions.anchorCount().call()
        except Exception as e:
            logger.warning("Failed to get anchor count: %s", e)
            return None

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"EthereumAnchor({status}, rpc={self.rpc_url})"
