"""
Compliance Verifier Module.

Implements the full auditor verification flow:
  1. Recompute event hash → compare with stored hash
  2. Verify Merkle inclusion proof
  3. Match computed Merkle root with on-chain root

Each step can be executed independently or as a combined full-audit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple

from .safety_event import SafetyEvent
from .hasher import hash_event
from .merkle_tree import MerkleTree
from .ethereum_anchor import EthereumAnchor

logger = logging.getLogger(__name__)


@dataclass
class AuditResult:
    """Comprehensive result of a full audit verification."""

    # Step 1: Hash integrity
    hash_valid: bool
    computed_hash: str
    expected_hash: str

    # Step 2: Merkle inclusion
    merkle_valid: bool
    computed_root: Optional[str] = None
    expected_root: Optional[str] = None

    # Step 3: On-chain match
    on_chain_valid: Optional[bool] = None
    on_chain_root: Optional[str] = None
    on_chain_available: bool = True

    # Overall
    @property
    def fully_verified(self) -> bool:
        """True only if all three steps passed."""
        if self.on_chain_valid is None:
            # On-chain check was skipped (no Ethereum)
            return self.hash_valid and self.merkle_valid
        return self.hash_valid and self.merkle_valid and self.on_chain_valid

    def summary(self) -> str:
        """Human-readable summary of verification results."""
        lines = [
            f"  Hash Integrity:    {'✅ PASS' if self.hash_valid else '❌ FAIL'}",
            f"  Merkle Inclusion:  {'✅ PASS' if self.merkle_valid else '❌ FAIL'}",
        ]
        if self.on_chain_valid is not None:
            lines.append(
                f"  On-Chain Match:    {'✅ PASS' if self.on_chain_valid else '❌ FAIL'}"
            )
        else:
            lines.append("  On-Chain Match:    ⚠️  SKIPPED (Ethereum unavailable)")

        status = "✅ VERIFIED" if self.fully_verified else "❌ TAMPERED / INCOMPLETE"
        lines.insert(0, f"Audit Result: {status}")
        return "\n".join(lines)


class ComplianceVerifier:
    """
    Auditor-facing verification interface.

    Allows independent verification of safety events against:
    - Their stored SHA-256 hashes (integrity)
    - Their Merkle proofs (batch inclusion)
    - The on-chain Merkle root (Ethereum finality)
    """

    # ------------------------------------------------------------------ #
    #  Step 1: Hash integrity
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_event_integrity(event_data: dict, expected_hash: str) -> bool:
        """
        Recompute the event hash and compare with the expected value.

        Parameters
        ----------
        event_data : dict
            The raw safety event dictionary.
        expected_hash : str
            The SHA-256 hex digest stored alongside the event.

        Returns
        -------
        bool
            True if the recomputed hash matches.
        """
        event = SafetyEvent.from_dict(event_data)
        computed = hash_event(event)
        match = computed == expected_hash
        if not match:
            logger.warning(
                "Hash mismatch: computed=%s, expected=%s", computed, expected_hash
            )
        return match

    # ------------------------------------------------------------------ #
    #  Step 2: Merkle inclusion
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_merkle_inclusion(
        event_hash: str,
        proof: List[Tuple[str, str]],
        expected_root: str,
    ) -> bool:
        """
        Verify that an event hash is included in a Merkle tree.

        Parameters
        ----------
        event_hash : str
            SHA-256 digest of the event.
        proof : list of (hash, direction) tuples
            Merkle proof from the batch manager.
        expected_root : str
            The expected Merkle root of the batch.

        Returns
        -------
        bool
            True if the proof validates.
        """
        return MerkleTree.verify_proof(event_hash, proof, expected_root)

    # ------------------------------------------------------------------ #
    #  Step 3: On-chain verification
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_on_chain(
        batch_id: int,
        expected_root: str,
        anchor_client: EthereumAnchor,
    ) -> Optional[bool]:
        """
        Verify a Merkle root against the Ethereum smart contract.

        Returns None if Ethereum is unavailable.
        """
        return anchor_client.verify_root(batch_id, expected_root)

    # ------------------------------------------------------------------ #
    #  Full audit
    # ------------------------------------------------------------------ #

    @classmethod
    def full_audit(
        cls,
        event_data: dict,
        expected_hash: str,
        proof: List[Tuple[str, str]],
        expected_root: str,
        batch_id: Optional[int] = None,
        anchor_client: Optional[EthereumAnchor] = None,
    ) -> AuditResult:
        """
        Execute the complete 3-step audit verification.

        Parameters
        ----------
        event_data : dict
            Raw safety event dictionary.
        expected_hash : str
            Stored event hash.
        proof : list of (hash, direction) tuples
            Merkle proof for the event.
        expected_root : str
            Expected Merkle root of the batch.
        batch_id : int, optional
            On-chain batch ID.
        anchor_client : EthereumAnchor, optional
            Ethereum client for on-chain verification.

        Returns
        -------
        AuditResult
            Comprehensive verification results.
        """
        # Step 1: Hash integrity
        event = SafetyEvent.from_dict(event_data)
        computed_hash = hash_event(event)
        hash_valid = computed_hash == expected_hash

        # Step 2: Merkle inclusion
        merkle_valid = MerkleTree.verify_proof(computed_hash, proof, expected_root)

        # Step 3: On-chain (optional)
        on_chain_valid = None
        on_chain_root = None
        on_chain_available = True

        if anchor_client is not None and batch_id is not None:
            record = anchor_client.get_anchor(batch_id)
            if record is not None:
                on_chain_root = record.merkle_root
                on_chain_valid = on_chain_root == expected_root
            else:
                on_chain_available = False
        else:
            on_chain_available = False

        result = AuditResult(
            hash_valid=hash_valid,
            computed_hash=computed_hash,
            expected_hash=expected_hash,
            merkle_valid=merkle_valid,
            computed_root=expected_root if merkle_valid else None,
            expected_root=expected_root,
            on_chain_valid=on_chain_valid,
            on_chain_root=on_chain_root,
            on_chain_available=on_chain_available,
        )

        logger.info("Audit completed:\n%s", result.summary())
        return result
