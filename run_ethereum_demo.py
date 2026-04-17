"""
End-to-End Ethereum Integration Demo.

This script demonstrates the full compliance pipeline connected to
a live Ethereum node (Hardhat local). It:

  1. Reads deployment info (contract address) from deployment.json
  2. Connects EthereumAnchor to the local Hardhat node
  3. Processes sample safety events through the pipeline
  4. Triggers batch anchoring → submits Merkle root on-chain
  5. Queries on-chain records to confirm anchoring
  6. Runs a full 3-step audit (hash → Merkle → on-chain verification)

Prerequisites:
  - Terminal 1: npx hardhat node
  - Terminal 2: npx hardhat run scripts/deploy.js --network localhost
  - Then:       python run_ethereum_demo.py
"""

import json
import os
import sys
import tempfile

# Load .env before importing our modules
from dotenv import load_dotenv
load_dotenv()

from blockchain_compliance.ethereum_anchor import EthereumAnchor
from blockchain_compliance.compliance_pipeline import CompliancePipeline


def load_deployment_info():
    """Read contract address from deployment.json."""
    deploy_path = os.path.join(os.path.dirname(__file__), "deployment.json")
    if not os.path.exists(deploy_path):
        print("ERROR: deployment.json not found.")
        print("Run these commands first:")
        print("  1. npx hardhat node          (in a separate terminal)")
        print("  2. npx hardhat run scripts/deploy.js --network localhost")
        sys.exit(1)

    with open(deploy_path, "r") as f:
        return json.load(f)


def main():
    print("=" * 70)
    print("  ETHEREUM INTEGRATION DEMO")
    print("  Compliance Pipeline + On-Chain Anchoring")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    #  Step 1: Load deployment info
    # ------------------------------------------------------------------ #
    deploy_info = load_deployment_info()
    contract_address = deploy_info["contractAddress"]
    print(f"\nContract address: {contract_address}")
    print(f"Authorized submitter: {deploy_info['authorizedSubmitter']}")

    # ------------------------------------------------------------------ #
    #  Step 2: Connect to Ethereum
    # ------------------------------------------------------------------ #
    print("\nConnecting to Ethereum...")
    anchor = EthereumAnchor(
        rpc_url=os.getenv("ETHEREUM_RPC_URL", "http://127.0.0.1:8545"),
        contract_address=contract_address,
        contract_abi_path=os.getenv(
            "COMPLIANCE_CONTRACT_ABI_PATH",
            "./blockchain_compliance/contracts/SafetyComplianceAnchor.abi.json"
        ),
        private_key=os.getenv("COMPLIANCE_PRIVATE_KEY"),
    )

    connected = anchor.connect()
    if not connected:
        print("ERROR: Could not connect to Ethereum node.")
        print("Make sure `npx hardhat node` is running.")
        sys.exit(1)

    print(f"Connected: {anchor}")
    print(f"On-chain anchor count (before): {anchor.get_anchor_count()}")

    # ------------------------------------------------------------------ #
    #  Step 3: Create pipeline with Ethereum anchoring
    # ------------------------------------------------------------------ #
    tmpdir = tempfile.mkdtemp(prefix="eth_demo_")
    pipeline = CompliancePipeline(
        db_path=os.path.join(tmpdir, "blocks.db"),
        events_db_path=os.path.join(tmpdir, "events.db"),
        batch_size=5,
        anchor_client=anchor,
    )

    # ------------------------------------------------------------------ #
    #  Step 4: Process safety events
    # ------------------------------------------------------------------ #
    sample_events = [
        {
            "timestamp": "2026-02-14T01:45:18.342Z",
            "tool_detected": True,
            "mq2": 387, "mq7": 142,
            "temperature": 38.5, "humidity": 65.0,
            "ir_detected": True,
            "fan_state": "ON",
            "risk_score": 0.82, "risk_level": "HIGH",
            "action_taken": "FAN_ACTIVATED",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:46:22.100Z",
            "tool_detected": True,
            "mq2": 415, "mq7": 158,
            "temperature": 42.0, "humidity": 72.0,
            "ir_detected": True,
            "fan_state": "ON",
            "risk_score": 0.91, "risk_level": "CRITICAL",
            "action_taken": "FAN_ACTIVATED",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:47:05.550Z",
            "tool_detected": False,
            "mq2": 120, "mq7": 45,
            "temperature": 30.0, "humidity": 55.0,
            "ir_detected": False,
            "fan_state": "ON",
            "risk_score": 0.35, "risk_level": "MEDIUM",
            "action_taken": "NONE",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:48:30.200Z",
            "tool_detected": False,
            "mq2": 55, "mq7": 22,
            "temperature": 26.0, "humidity": 45.0,
            "ir_detected": False,
            "fan_state": "OFF",
            "risk_score": 0.10, "risk_level": "LOW",
            "action_taken": "FAN_DEACTIVATED",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:50:00.000Z",
            "tool_detected": True,
            "mq2": 510, "mq7": 200,
            "temperature": 48.0, "humidity": 80.0,
            "ir_detected": True,
            "fan_state": "ON",
            "risk_score": 0.95, "risk_level": "CRITICAL",
            "action_taken": "FAN_ACTIVATED",
            "sensor_node_id": "ESP32-NODE-02",
        },
    ]

    print(f"\nProcessing {len(sample_events)} safety events (batch_size=5)...\n")
    results = []
    for i, event_data in enumerate(sample_events, 1):
        result = pipeline.process_event(event_data)
        results.append(result)
        print(f"  Event {i}: hash={result['event_hash'][:24]}...  block={result['block_index']}")
        if result.get("batch_triggered"):
            print(f"           BATCH TRIGGERED -> root={result['merkle_root'][:24]}...")
            print(f"           Merkle root anchored to Ethereum!")

    # ------------------------------------------------------------------ #
    #  Step 5: Query on-chain records
    # ------------------------------------------------------------------ #
    print("\n" + "-" * 70)
    print("  ON-CHAIN VERIFICATION")
    print("-" * 70)

    anchor_count = anchor.get_anchor_count()
    print(f"\nOn-chain anchor count (after): {anchor_count}")

    if anchor_count and anchor_count > 0:
        record = anchor.get_anchor(0)
        if record:
            print(f"\nAnchor Record #0:")
            print(f"  Merkle Root:  {record.merkle_root}")
            print(f"  Timestamp:    {record.timestamp}")
            print(f"  Batch ID:     {record.batch_id}")

            # Verify on-chain
            batch_record = pipeline.batch_manager.get_batch(0)
            if batch_record:
                on_chain_match = anchor.verify_root(0, batch_record.merkle_root)
                print(f"\n  On-chain root matches local root: {on_chain_match}")

    # ------------------------------------------------------------------ #
    #  Step 6: Full 3-step audit
    # ------------------------------------------------------------------ #
    print("\n" + "-" * 70)
    print("  FULL 3-STEP AUDIT")
    print("-" * 70)

    event_id = results[0]["event_id"]
    print(f"\nAuditing event: {event_id}")

    audit = pipeline.audit_event(event_id, batch_index=0)
    if audit:
        print(f"\n  Step 1 - Hash Integrity:    {'PASS' if audit.hash_valid else 'FAIL'}")
        print(f"    Computed: {audit.computed_hash[:32]}...")
        print(f"    Expected: {audit.expected_hash[:32]}...")

        print(f"\n  Step 2 - Merkle Inclusion:  {'PASS' if audit.merkle_valid else 'FAIL'}")

        if audit.on_chain_valid is not None:
            print(f"\n  Step 3 - On-Chain Match:   {'PASS' if audit.on_chain_valid else 'FAIL'}")
            if audit.on_chain_root:
                print(f"    On-chain root: {audit.on_chain_root[:32]}...")
        else:
            print(f"\n  Step 3 - On-Chain Match:   SKIPPED (no on-chain data)")

        status = "FULLY VERIFIED" if audit.fully_verified else "VERIFICATION FAILED"
        print(f"\n  Overall: {status}")

    # ------------------------------------------------------------------ #
    #  Summary
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 70)
    chain_status = pipeline.get_chain_status()
    print(f"  Local chain:     {chain_status['chain_length']} blocks, valid={chain_status['chain_valid']}")
    print(f"  Batches:         {chain_status['total_batches']}")
    print(f"  Ethereum:        {'Connected' if chain_status['ethereum_connected'] else 'Disconnected'}")
    print(f"  Data directory:  {tmpdir}")
    print("=" * 70)

    pipeline.shutdown()


if __name__ == "__main__":
    main()
