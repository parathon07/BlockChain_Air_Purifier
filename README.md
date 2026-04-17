# Blockchain Compliance Layer — IoT Air Purifier Safety System

A tamper-proof, cryptographically verifiable compliance logging system for real-time IoT safety monitoring. Safety events from sensor nodes are hashed, chained in a local blockchain, batched into Merkle trees, and anchored to Ethereum for public auditability.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      PHYSICAL SAFETY LAYER                       │
│  ESP32 Sensors → MQ2/MQ7 readings → AI inference → Fan control  │
└──────────────────────┬───────────────────────────────────────────┘
                       │  safety event (JSON)
┌──────────────────────▼───────────────────────────────────────────┐
│                       DECISION LAYER                             │
│  Risk score computation → Trigger logic → Safety event creation  │
└──────────────────────┬───────────────────────────────────────────┘
                       │  event dict
┌──────────────────────▼───────────────────────────────────────────┐
│                   TRUST LAYER (Blockchain)                        │
│                                                                   │
│  1. SafetyEvent ─────► SHA-256 Hash                              │
│                           │                                       │
│  2. Hash ────────────► Local Blockchain (SQLite, append-only)    │
│                           │                                       │
│  3. Hash ────────────► Batch Manager (accumulate N hashes)       │
│                           │                                       │
│  4. Batch ───────────► Merkle Tree → single root hash           │
│                           │                                       │
│  5. Merkle Root ─────► Ethereum Smart Contract (on-chain)        │
│                                                                   │
│  6. Auditor verifies: hash ✓ → Merkle proof ✓ → on-chain ✓     │
└──────────────────────────────────────────────────────────────────┘
```

### Design Principles

| Principle                | Implementation                                                               |
| ------------------------ | ---------------------------------------------------------------------------- |
| **Safety never blocked** | Blockchain runs asynchronously; fan activation is never delayed by anchoring |
| **Tamper-proof**         | SHA-256 hashing + block chaining + Merkle trees + Ethereum immutability      |
| **Cost-efficient**       | Only Merkle roots go on-chain (1 tx per 100 events by default)               |
| **Publicly verifiable**  | Anyone with the event data can independently verify the full chain           |

---

## Project Structure

```
BlockChain_Air_Purifier/
├── blockchain_compliance/          # Python compliance package
│   ├── __init__.py
│   ├── __main__.py                 # Package entry point (demo)
│   ├── config.py                   # Environment-based configuration
│   ├── safety_event.py             # SafetyEvent dataclass + canonical JSON
│   ├── hasher.py                   # SHA-256 hashing utilities
│   ├── blockchain.py               # Local append-only blockchain (SQLite)
│   ├── merkle_tree.py              # Merkle tree construction + proofs
│   ├── batch_manager.py            # Thread-safe batch accumulation
│   ├── ethereum_anchor.py          # Web3.py client for on-chain anchoring
│   ├── compliance_pipeline.py      # End-to-end orchestrator
│   ├── verifier.py                 # 3-step auditor verification flow
│   └── contracts/
│       └── SafetyComplianceAnchor.abi.json
│
├── contracts/
│   └── SafetyComplianceAnchor.sol  # Solidity smart contract
│
├── scripts/
│   └── deploy.js                   # Hardhat deployment script
│
├── tests/                          # Pytest test suite (76 tests)
│   ├── test_safety_event.py
│   ├── test_hasher.py
│   ├── test_blockchain.py
│   ├── test_merkle_tree.py
│   ├── test_batch_manager.py
│   ├── test_compliance_pipeline.py
│   └── test_verifier.py
│
├── .env                            # Ethereum configuration
├── hardhat.config.js               # Hardhat node config
├── requirements.txt                # Python dependencies
├── package.json                    # Node.js dependencies
├── deployment.json                 # Auto-generated after contract deploy
├── run_ethereum_demo.py            # Full end-to-end Ethereum demo
└── blockchain_compliance_architecture.md  # Detailed architecture document
```

---

## Workflow — How Events Flow Through the System

```
   Sensor reading arrives
          │
          ▼
   ┌─────────────────┐
   │  SafetyEvent     │  Create structured event with timestamp,
   │  (safety_event)  │  sensor data, risk score, fan state
   └────────┬─────────┘
            │
            ▼
   ┌─────────────────┐
   │   SHA-256 Hash   │  Deterministic hash of canonical JSON
   │   (hasher)       │  → unique fingerprint per event
   └────────┬─────────┘
            │
       ┌────┴────┐
       ▼         ▼
  ┌─────────┐  ┌──────────────┐
  │ Local    │  │ Batch Manager │
  │ Chain    │  │ (accumulate)  │
  │ (SQLite) │  └──────┬───────┘
  └─────────┘         │  when batch_size reached
                       ▼
              ┌──────────────────┐
              │   Merkle Tree     │  Build tree from N hashes
              │   → single root   │  → compress to 1 commitment
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  Ethereum Anchor  │  Submit root to smart contract
              │  (web3.py → tx)   │  → immutable public record
              └──────────────────┘
```

### Verification Flow (Auditor)

1. **Hash Integrity** — Recompute SHA-256 from raw event data, compare with stored hash
2. **Merkle Inclusion** — Verify the event hash is in the batch using a Merkle proof
3. **On-Chain Match** — Confirm the Merkle root matches what's stored on Ethereum

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** and npm
- pip packages: `web3`, `python-dotenv`, `pytest`

### 1. Install Dependencies

```bash
# Python
pip install -r requirements.txt

# Node.js (Hardhat)
npm install
```

### 2. Run Unit Tests (no Ethereum needed)

```bash
python -m pytest tests/ -v
```

All 76 tests should pass.

### 3. Run Offline Demo (no Ethereum needed)

```bash
python -m blockchain_compliance
```

Processes 5 sample events through the full pipeline using a temporary SQLite database.

### 4. Run with Ethereum (Full Integration)

**Terminal 1** — Start the local Ethereum node:

```bash
npx hardhat node
```

**Terminal 2** — Deploy the smart contract:

```bash
npx hardhat run scripts/deploy.js --network localhost
```

**Terminal 2** — Run the end-to-end integration demo:

```bash
python run_ethereum_demo.py
```

This will:

- Connect to the local Hardhat node
- Process 5 safety events → trigger a batch at event #5
- Anchor the Merkle root on-chain via a transaction
- Query the on-chain record
- Run a full 3-step audit (hash → Merkle → on-chain) → **FULLY VERIFIED**

---

## Configuration

All settings are loaded from environment variables (`.env` file). Key variables:

| Variable                       | Default                                                             | Description                        |
| ------------------------------ | ------------------------------------------------------------------- | ---------------------------------- |
| `BATCH_SIZE`                   | `100`                                                               | Events per Merkle tree batch       |
| `ETHEREUM_RPC_URL`             | `http://127.0.0.1:8545`                                             | Ethereum JSON-RPC endpoint         |
| `COMPLIANCE_CONTRACT_ADDRESS`  | —                                                                   | Deployed contract address          |
| `COMPLIANCE_PRIVATE_KEY`       | —                                                                   | Wallet private key for signing txs |
| `COMPLIANCE_CONTRACT_ABI_PATH` | `./blockchain_compliance/contracts/SafetyComplianceAnchor.abi.json` | Path to contract ABI               |
| `COMPLIANCE_DB_PATH`           | `./data/blocks.db`                                                  | Local blockchain SQLite path       |
| `COMPLIANCE_EVENTS_DB_PATH`    | `./data/events.db`                                                  | Events SQLite path                 |

---

## Smart Contract

**`SafetyComplianceAnchor.sol`** — Minimal, gas-efficient contract with 3 core functions:

| Function                                              | Type  | Description                        |
| ----------------------------------------------------- | ----- | ---------------------------------- |
| `submitAnchor(bytes32 _merkleRoot)`                   | Write | Store a Merkle root on-chain       |
| `getAnchor(uint256 _batchId)`                         | Read  | Retrieve anchor record by batch ID |
| `verifyRoot(uint256 _batchId, bytes32 _expectedRoot)` | Read  | Check if a root matches on-chain   |

Access control: Only the `authorizedSubmitter` (set at deployment) can call `submitAnchor`.

---

## Completion Status

| Component           | Status           | Details                                             |
| ------------------- | ---------------- | --------------------------------------------------- |
| Safety Event module | ✅ Complete      | Dataclass, canonical JSON, validation               |
| SHA-256 Hasher      | ✅ Complete      | Event, string, bytes, pairwise hashing              |
| Local Blockchain    | ✅ Complete      | SQLite persistence, genesis block, chain validation |
| Merkle Tree         | ✅ Complete      | Construction, root, proof generation & verification |
| Ethereum Anchor     | ✅ Complete      | Web3.py client, retry logic, graceful fallback      |
| Batch Manager       | ✅ Complete      | Thread-safe, size + time triggers, disk persistence |
| Compliance Pipeline | ✅ Complete      | End-to-end orchestrator, events DB, audit           |
| Verifier            | ✅ Complete      | 3-step audit flow (hash → Merkle → on-chain)        |
| Solidity Contract   | ✅ Complete      | Deployed and tested on local Hardhat                |
| Hardhat Integration | ✅ Complete      | Config, deploy script, local node                   |
| Unit Tests          | ✅ 76/76 passing | 7 test files covering all modules                   |
| Ethereum E2E Test   | ✅ Verified      | On-chain anchoring + full audit passed              |

---

## Security Model

```
Layer 1: SHA-256 hash integrity     → detects any event modification
Layer 2: Block chaining             → detects insertion/deletion/reordering
Layer 3: Merkle tree aggregation    → efficient batch verification
Layer 4: Ethereum anchoring         → public immutability + timestamping
Layer 5: Authorized submitter       → only the designated wallet can anchor
```

> **Trust boundary**: The real-time safety control path (sensor → AI → fan) is completely independent from the blockchain compliance path. Safety operations are **never** blocked by blockchain latency or failures.

---

## License

ISC
