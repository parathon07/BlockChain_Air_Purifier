# Blockchain-Based Compliance Layer for Real-Time IoT Safety Monitoring

> A Hybrid Anchoring Architecture for Tamper-Proof Safety Certification

---

## Table of Contents

1. [Architectural Role of Blockchain](#1-architectural-role-of-blockchain)
2. [Problem Statement](#2-problem-statement)
3. [Safety Event Lifecycle](#3-safety-event-lifecycle)
4. [Merkle Tree Batching](#4-merkle-tree-batching)
5. [Ethereum Anchoring](#5-ethereum-anchoring)
6. [Full System Flow Diagram](#6-full-system-flow-diagram)
7. [Security Model](#7-security-model)
8. [Scalability Considerations](#8-scalability-considerations)
9. [Verification Model](#9-verification-model)
10. [Implementation Preparation Checklist](#10-implementation-preparation-checklist)
11. [High-Level Summary](#11-high-level-summary)

---

## 1. Architectural Role of Blockchain

### Why Blockchain Exists in This System

This system is a **three-layer safety architecture** that combines physical sensing, intelligent decision-making, and cryptographic trust. Each layer has a precise boundary of responsibility:

| Layer                        | Responsibility                                       | Latency Requirement                |
| ---------------------------- | ---------------------------------------------------- | ---------------------------------- |
| **Physical Safety Layer**    | Sensor acquisition, AI inference, fan activation     | < 100ms (hard real-time)           |
| **Decision Layer**           | Risk scoring, trigger logic, safety event generation | < 500ms (soft real-time)           |
| **Trust Layer (Blockchain)** | Certifies safety actions, ensures log integrity      | Seconds to minutes (non-real-time) |

The blockchain layer exists for **one purpose**: to create **verifiable, tamper-proof records** that prove safety actions were taken correctly, at the correct time, in response to detected hazards.

> [!IMPORTANT]
> **The blockchain does NOT control hardware.** It does not activate fans, read sensors, or make safety decisions. It is a **post-decision certification mechanism** — a notary, not a controller.

### What Are "Verifiable Safety Records"?

A **verifiable safety record** is a digitally signed, cryptographically anchored data structure that satisfies three properties:

1. **Integrity** — The record has not been modified since creation (SHA-256 hash verification).
2. **Ordering** — The record's position in the event timeline is provable (block chaining).
3. **Existence** — The record's existence at a specific point in time can be independently verified by any third party (Ethereum anchoring).

These records constitute the system's **compliance trail** — the evidence that the system operated correctly, auditable by regulatory bodies, insurers, or the public.

---

## 2. Problem Statement

### What Blockchain Solves in Compliance Systems

Traditional safety systems store logs in **centralized databases** — PostgreSQL, SQLite, cloud services. This introduces fundamental trust vulnerabilities:

#### 2.1 Log Tampering

A system administrator, malicious insider, or compromised process can **modify log entries** after the fact. For example:

- Changing a `risk_score` from `0.95` (critical) to `0.30` (safe) to conceal a near-miss event.
- Deleting entries where the fan failed to activate despite hazardous gas levels.
- Backdating timestamps to fabricate compliance during an audit window.

In a traditional database, **there is no cryptographic proof that a record has not been altered**.

#### 2.2 Admin Data Manipulation

Database administrators have full CRUD access. Even with access controls and audit trails, the audit trail itself is stored in the same system — and is therefore equally mutable. This is a **circular trust problem**: the system that generates evidence is the same system that could destroy it.

#### 2.3 Lack of Transparency

Stakeholders (regulators, building occupants, insurance companies) have **no independent mechanism** to verify that the safety system operated correctly. They must trust the operator's word — a trust model that breaks down in adversarial or negligent scenarios.

#### 2.4 Compliance Fraud

In regulated environments (OSHA, EPA, building safety codes), operators can fabricate entire compliance histories. Without an external anchor, **there is no difference between a real log and a forged one**.

### Why a Traditional Database Is Insufficient

| Property                   | Traditional DB                               | Blockchain Layer                                      |
| -------------------------- | -------------------------------------------- | ----------------------------------------------------- |
| Append-only guarantee      | ❌ Admin can UPDATE/DELETE                   | ✅ Chained hashes detect mutation                     |
| Independent verification   | ❌ Requires trust in operator                | ✅ Public Ethereum anchor is independently verifiable |
| Tamper evidence            | ❌ No cryptographic proof of integrity       | ✅ SHA-256 + Merkle tree + on-chain root              |
| Decentralized timestamping | ❌ System clock is operator-controlled       | ✅ Ethereum block timestamp is consensus-derived      |
| Regulatory defensibility   | ⚠️ Weak — "we didn't change it" is not proof | ✅ Strong — mathematical proof of integrity           |

A traditional database answers: _"Here is what we recorded."_
A blockchain-anchored system answers: _"Here is what we recorded, and here is mathematical proof that no one has altered it since."_

---

## 3. Safety Event Lifecycle

The lifecycle of a safety event from sensor reading to immutable record follows three discrete steps.

### Step 1 — Safety Event Creation

When the Decision Layer computes a risk score and takes action (or decides no action is needed), it generates a **Safety Event Object** — a structured JSON record capturing the full state at that instant.

**Example JSON Structure:**

```json
{
  "event_id": "evt-20260214-014518-a3f7",
  "timestamp": "2026-02-14T01:45:18.342Z",
  "tool_detected": true,
  "mq2": 387,
  "mq7": 142,
  "fan_state": "ON",
  "risk_score": 0.82,
  "risk_level": "HIGH",
  "action_taken": "FAN_ACTIVATED",
  "sensor_node_id": "ESP32-NODE-01"
}
```

| Field            | Type       | Description                                                 |
| ---------------- | ---------- | ----------------------------------------------------------- |
| `event_id`       | `string`   | Unique identifier for this event                            |
| `timestamp`      | `ISO-8601` | UTC timestamp of event creation                             |
| `tool_detected`  | `boolean`  | Whether the tool/activity detection model fired             |
| `mq2`            | `integer`  | MQ2 gas sensor reading (smoke/combustible gases)            |
| `mq7`            | `integer`  | MQ7 gas sensor reading (carbon monoxide)                    |
| `fan_state`      | `string`   | Current state of the exhaust fan: `"ON"` or `"OFF"`         |
| `risk_score`     | `float`    | Computed risk score in range `[0.0, 1.0]`                   |
| `risk_level`     | `string`   | Categorical risk: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`       |
| `action_taken`   | `string`   | Action executed: `FAN_ACTIVATED`, `FAN_DEACTIVATED`, `NONE` |
| `sensor_node_id` | `string`   | Identifier of the originating ESP32 sensor node             |

> [!NOTE]
> This event object is created **after** the safety action has already been executed. The fan is already running. The blockchain layer receives this as a **report of what happened**, not as a command.

### Step 2 — Event Hashing (SHA-256)

The event JSON is **canonicalized** (keys sorted, no whitespace variation) and hashed using SHA-256.

**Process:**

```
canonical_json = json.dumps(event, sort_keys=True, separators=(',', ':'))
event_hash = SHA-256(canonical_json)
```

**Conceptual Example:**

```
Input (canonical):
{"action_taken":"FAN_ACTIVATED","event_id":"evt-20260214-014518-a3f7","fan_state":"ON","mq2":387,"mq7":142,"risk_level":"HIGH","risk_score":0.82,"sensor_node_id":"ESP32-NODE-01","timestamp":"2026-02-14T01:45:18.342Z","tool_detected":true}

Output (SHA-256):
a4b7c3d9e1f2038476a5b9c8d7e6f50412398765fedcba0987654321abcdef12
```

**Integrity Guarantee:**

- SHA-256 produces a **256-bit (64-hex-character) digest** that is deterministic: the same input always produces the same hash.
- Any modification to the event — even changing a single bit — produces a **completely different hash** (avalanche effect).
- It is computationally infeasible to find a different input that produces the same hash (collision resistance).
- The hash acts as a **digital fingerprint**: if you have the original event and the hash, you can verify integrity. If someone alters the event, the hash will not match.

### Step 3 — Local Blockchain Structure

The event hash is inserted into a **local blockchain** — an append-only chain of blocks maintained on the Raspberry Pi (or equivalent edge server).

**Block Structure:**

```
Block {
    index:          uint64       // Sequential block number (0, 1, 2, ...)
    timestamp:      ISO-8601     // Time the block was created
    event_hash:     bytes32      // SHA-256 hash of the safety event
    previous_hash:  bytes32      // Hash of the previous block in the chain
    block_hash:     bytes32      // SHA-256(index + timestamp + event_hash + previous_hash)
}
```

**Example Chain:**

```
┌──────────────────────────────┐
│ Block 0 (Genesis)            │
│ index: 0                     │
│ timestamp: 2026-02-14T00:00  │
│ event_hash: 0x0000...0000    │
│ previous_hash: 0x0000...0000 │
│ block_hash: 0x7a3f...c1d2    │──┐
└──────────────────────────────┘  │
                                  │
┌──────────────────────────────┐  │
│ Block 1                      │  │
│ index: 1                     │  │
│ timestamp: 2026-02-14T01:45  │  │
│ event_hash: 0xa4b7...ef12    │  │
│ previous_hash: 0x7a3f...c1d2 │←─┘
│ block_hash: 0x9e2d...f8a1    │──┐
└──────────────────────────────┘  │
                                  │
┌──────────────────────────────┐  │
│ Block 2                      │  │
│ index: 2                     │  │
│ timestamp: 2026-02-14T01:46  │  │
│ event_hash: 0xb5c8...d023    │  │
│ previous_hash: 0x9e2d...f8a1 │←─┘
│ block_hash: 0x1f4e...a7b3    │
└──────────────────────────────┘
```

**Chaining and Tamper Detection:**

Each block contains the `previous_hash` — the `block_hash` of the block that precedes it. This creates a **cryptographic chain**: if an attacker modifies any field in Block 1, its `block_hash` changes. But Block 2's `previous_hash` still contains the _original_ hash of Block 1. The mismatch is **immediately detectable**.

To tamper with Block 1 without detection, the attacker must also recompute Block 2, then Block 3, then every subsequent block. This cascading recomputation makes tampering evident and, when combined with Ethereum anchoring, **provably impossible** to conceal.

---

## 4. Merkle Tree Batching

### Why Batching Is Required

Storing every individual event hash on Ethereum would be prohibitively expensive. At current gas prices, a single `SSTORE` operation (storing 32 bytes on-chain) costs approximately **20,000 gas** (~$0.50–$2.00 depending on network conditions). A system generating one event per minute would produce **1,440 events/day**, costing **$720–$2,880/day** in gas fees.

This is economically unsustainable. The solution is **cryptographic batching**: compress N events into a single 32-byte value that can be stored on-chain for the same gas cost as one event.

### How Merkle Trees Work

A **Merkle tree** is a binary tree of hashes. It takes an arbitrary number of inputs and produces a single **root hash** that cryptographically represents all inputs.

**Construction Process (for a batch of 4 events):**

```
Step 1: Start with leaf hashes (event hashes from local blockchain)

  H(E1)       H(E2)       H(E3)       H(E4)
   │            │            │            │
   └─────┬──────┘            └─────┬──────┘
         │                         │
Step 2: Pairwise hashing — combine adjacent pairs

    H(H(E1) + H(E2))        H(H(E3) + H(E4))
         = H12                    = H34
           │                        │
           └──────────┬─────────────┘
                      │
Step 3: Root generation — hash the intermediate nodes

              H(H12 + H34)
                = ROOT
```

**Pairwise Hashing:**

At each level of the tree, adjacent hashes are **concatenated** and re-hashed:

```
H12 = SHA-256( H(E1) || H(E2) )
H34 = SHA-256( H(E3) || H(E4) )
ROOT = SHA-256( H12 || H34 )
```

Where `||` denotes concatenation.

### Why the Root Represents All Events

The Merkle root is a **deterministic function** of all leaf values. If any single event is modified, its leaf hash changes, which changes the intermediate hash, which changes the root. Therefore:

- The root is a **fixed-size (32-byte) commitment** to the entire batch.
- Verifying the root is equivalent to verifying all events in the batch.
- This is **cryptographic compression**: N events → 1 hash, with no loss of integrity guarantees.

### How Proof-of-Inclusion Works (Conceptually)

To prove that a specific event (e.g., E2) is included in a batch without revealing the other events, a **Merkle proof** is constructed:

```
To prove E2 is in the tree:

Provide:  H(E2), H(E1), H34

Verifier computes:
  1. H12 = SHA-256( H(E1) || H(E2) )     ← uses provided H(E1) + H(E2)
  2. ROOT' = SHA-256( H12 || H34 )        ← uses computed H12 + provided H34
  3. Compare ROOT' with stored ROOT        ← match = inclusion proven
```

The proof requires only **O(log N)** hashes (for N events), making verification extremely efficient. This enables an auditor to verify a single event's inclusion without needing the entire batch dataset.

---

## 5. Ethereum Anchoring

### What Gets Stored On-Chain

**Only the Merkle root** is stored on Ethereum — not the raw event data, not the individual event hashes, not the local blockchain. The smart contract stores three fields per batch:

```solidity
struct AnchorRecord {
    bytes32 merkle_root;    // Merkle root of the event batch
    uint256 timestamp;      // Block timestamp when anchored
    uint256 batch_id;       // Sequential batch identifier
}
```

### Why Not Raw Event Data

| Approach             | On-Chain Storage per Day (1440 events) | Gas Cost / Day |
| -------------------- | -------------------------------------- | -------------- |
| Every raw event      | ~1,440 × ~500 bytes = 720 KB           | $50,000+       |
| Every event hash     | 1,440 × 32 bytes = 46 KB               | $720–$2,880    |
| **Merkle root only** | **1–10 × 32 bytes = 32–320 bytes**     | **$1–$20**     |

Storing the Merkle root achieves **the same cryptographic guarantee** as storing every event individually, at a fraction of the cost.

### Smart Contract Interface

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract SafetyComplianceAnchor {

    struct AnchorRecord {
        bytes32 merkleRoot;
        uint256 timestamp;
        uint256 batchId;
    }

    mapping(uint256 => AnchorRecord) public anchors;
    uint256 public anchorCount;
    address public authorizedSubmitter;

    event AnchorSubmitted(
        uint256 indexed batchId,
        bytes32 merkleRoot,
        uint256 timestamp
    );

    modifier onlyAuthorized() {
        require(msg.sender == authorizedSubmitter, "Unauthorized");
        _;
    }

    constructor(address _submitter) {
        authorizedSubmitter = _submitter;
    }

    function submitAnchor(bytes32 _merkleRoot) external onlyAuthorized {
        uint256 batchId = anchorCount;
        anchors[batchId] = AnchorRecord({
            merkleRoot: _merkleRoot,
            timestamp: block.timestamp,
            batchId: batchId
        });
        anchorCount++;
        emit AnchorSubmitted(batchId, _merkleRoot, block.timestamp);
    }

    function getAnchor(uint256 _batchId)
        external view returns (bytes32, uint256, uint256)
    {
        AnchorRecord memory record = anchors[_batchId];
        return (record.merkleRoot, record.timestamp, record.batchId);
    }

    function verifyRoot(uint256 _batchId, bytes32 _expectedRoot)
        external view returns (bool)
    {
        return anchors[_batchId].merkleRoot == _expectedRoot;
    }
}
```

### Hybrid Anchoring Architecture — Definition

This design is a **Hybrid Anchoring Architecture**:

- **Local layer**: Full event data + local blockchain (high resolution, low cost, private).
- **Public layer**: Cryptographic commitment only (low resolution, moderate cost, public and immutable).

The local layer provides **operational detail**. The public layer provides **trust and finality**. Together, they deliver the guarantees of a public blockchain at the cost profile of a private system.

```
┌──────────────────────────────────────────────┐
│              HYBRID ARCHITECTURE             │
├──────────────────────────────────────────────┤
│                                              │
│   LOCAL (Private, Full Resolution)           │
│   ┌─────────────────────────────────┐        │
│   │ Raw Events → Event Hashes →     │        │
│   │ Local Blockchain → Merkle Trees │        │
│   └───────────────┬─────────────────┘        │
│                   │ Merkle Root               │
│                   ▼                           │
│   PUBLIC (Ethereum, Commitment Only)         │
│   ┌─────────────────────────────────┐        │
│   │ merkle_root + timestamp +       │        │
│   │ batch_id                        │        │
│   └─────────────────────────────────┘        │
│                                              │
└──────────────────────────────────────────────┘
```

---

## 6. Full System Flow Diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║                    END-TO-END SYSTEM PIPELINE                       ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║   ESP32 Sensor Nodes                                                 ║
║   ┌────────────────────┐                                             ║
║   │ MQ2, MQ7, Tool Det │                                             ║
║   │ (Physical Safety)  │                                             ║
║   └────────┬───────────┘                                             ║
║            │ MQTT                                                    ║
║            ▼                                                         ║
║   Raspberry Pi (Edge Server)                                         ║
║   ┌────────────────────────────────────────────────┐                 ║
║   │                                                │                 ║
║   │  ┌──────────────┐    ┌───────────────────┐     │                 ║
║   │  │ AI Detection  │───▶│ Risk Calculation  │     │                 ║
║   │  │ (Inference)   │    │ (Score + Level)   │     │                 ║
║   │  └──────────────┘    └────────┬──────────┘     │                 ║
║   │                               │                 │                 ║
║   │                   ┌───────────┴──────────┐      │                 ║
║   │                   │                      │      │                 ║
║   │                   ▼                      ▼      │                 ║
║   │          ┌──────────────┐    ┌────────────────┐ │                 ║
║   │          │  Fan Control  │    │ Safety Event   │ │                 ║
║   │          │  (GPIO/Relay) │    │ Object (JSON)  │ │                 ║
║   │          └──────────────┘    └───────┬────────┘ │                 ║
║   │            (REAL-TIME PATH)          │          │                 ║
║   │                                      │          │                 ║
║   │   ═══════════════ TRUST BOUNDARY ════╪══════    │                 ║
║   │            (ASYNC COMPLIANCE PATH)   │          │                 ║
║   │                                      ▼          │                 ║
║   │                           ┌────────────────┐    │                 ║
║   │                           │ Event Hashing  │    │                 ║
║   │                           │ (SHA-256)      │    │                 ║
║   │                           └───────┬────────┘    │                 ║
║   │                                   ▼             │                 ║
║   │                        ┌────────────────────┐   │                 ║
║   │                        │ Local Blockchain   │   │                 ║
║   │                        │ (Append-Only Chain)│   │                 ║
║   │                        └───────┬────────────┘   │                 ║
║   │                                │                │                 ║
║   │                  ┌─────────────┴──────────┐     │                 ║
║   │                  │ Batch Accumulator       │     │                 ║
║   │                  │ (Collect N events)      │     │                 ║
║   │                  └─────────────┬──────────┘     │                 ║
║   │                                ▼                │                 ║
║   │                  ┌───────────────────────┐      │                 ║
║   │                  │ Merkle Tree Builder   │      │                 ║
║   │                  │ → Root Generation     │      │                 ║
║   │                  └───────────┬───────────┘      │                 ║
║   │                              │                  │                 ║
║   └──────────────────────────────┼──────────────────┘                 ║
║                                  │                                    ║
║                                  ▼                                    ║
║                  ┌───────────────────────────┐                        ║
║                  │ Ethereum Smart Contract   │                        ║
║                  │ submitAnchor(merkle_root)  │                        ║
║                  │                           │                        ║
║                  │ Stores:                   │                        ║
║                  │  • merkle_root            │                        ║
║                  │  • timestamp              │                        ║
║                  │  • batch_id               │                        ║
║                  └───────────┬───────────────┘                        ║
║                              │                                        ║
║                              ▼                                        ║
║                  ┌───────────────────────────┐                        ║
║                  │ Dashboard Verification    │                        ║
║                  │ (Public Audit Interface)  │                        ║
║                  │                           │                        ║
║                  │  • View events            │                        ║
║                  │  • Verify hashes          │                        ║
║                  │  • Check on-chain anchors │                        ║
║                  │  • Validate Merkle proofs │                        ║
║                  └───────────────────────────┘                        ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

**Critical Observation: The Trust Boundary**

The diagram shows a clear **trust boundary** separating two paths:

- **Real-Time Path** (Fan Control): Sub-100ms latency, no blockchain dependency, operates even if Ethereum is down.
- **Async Compliance Path** (Blockchain): Seconds to minutes latency, processes events after safety actions are taken, can tolerate network delays.

**The fan never waits for the blockchain. The blockchain never controls the fan.**

---

## 7. Security Model

The security model is **layered and defense-in-depth**, with each layer providing independent guarantees:

### Layer 1: SHA-256 Integrity (Event Level)

```
Event JSON → SHA-256 → event_hash (32 bytes)
```

- **Guarantees**: Any modification to the event data produces a different hash.
- **Threat mitigated**: Undetected alteration of individual events.
- **Strength**: SHA-256 has no known practical collision attacks. Pre-image resistance is 2^256 operations.

### Layer 2: Block Chaining (Sequence Level)

```
Block N: block_hash = SHA-256(index + timestamp + event_hash + previous_hash)
Block N+1: previous_hash = Block N's block_hash
```

- **Guarantees**: Events are cryptographically ordered. Inserting, deleting, or reordering events breaks the chain.
- **Threat mitigated**: Event reordering, insertion of fabricated events, deletion of inconvenient events.
- **Strength**: Tampering with block K requires recomputation of all blocks K+1 through N.

### Layer 3: Merkle Aggregation (Batch Level)

```
N event hashes → Merkle Tree → Single root hash (32 bytes)
```

- **Guarantees**: A single root hash commits to all events in the batch. Any alteration invalidates the root.
- **Threat mitigated**: Selective tampering within a batch, difficulty of proving individual event inclusion.
- **Strength**: O(log N) proof size for individual event verification. Efficient and scalable.

### Layer 4: Ethereum Timestamping (Global Level)

```
Merkle root → submitAnchor() → Stored on Ethereum mainnet
```

- **Guarantees**: The Merkle root is timestamped by Ethereum's consensus mechanism. Once confirmed, it is immutable.
- **Threat mitigated**: Operator claiming events occurred at different times, wholesale fabrication of compliance history.
- **Strength**: Ethereum's proof-of-stake consensus with 400,000+ validators. Rewriting history requires controlling >⅓ of staked ETH (~$50B+).

### Layer 5: Decentralized Immutability (Systemic Level)

```
Ethereum state is replicated across ~7,000+ full nodes worldwide.
```

- **Guarantees**: No single entity can alter or delete the anchored data. The record persists as long as Ethereum exists.
- **Threat mitigated**: Centralized deletion, government seizure, operator negligence, data center failure.
- **Strength**: The compliance record survives the destruction of the original system.

### Why This Is Compliance Infrastructure, Not Hype

This is not "blockchain for the sake of blockchain." Each layer addresses a **specific, auditable threat vector**:

| Threat                                   | Traditional System             | This Architecture                          |
| ---------------------------------------- | ------------------------------ | ------------------------------------------ |
| Admin alters a log entry                 | Undetectable                   | SHA-256 hash mismatch                      |
| Events reordered to hide response delay  | Possible                       | Chain break detected                       |
| Operator fabricates compliance history   | No external verification       | Ethereum anchor provides independent proof |
| Auditor cannot verify independently      | Must trust operator's database | Public on-chain verification               |
| System destroyed (fire, flood, sabotage) | Logs lost forever              | Ethereum anchors survive globally          |

This architecture exists because **compliance requires proof, and proof requires independence from the entity being audited**.

---

## 8. Scalability Considerations

### 8.1 Batch Size Tuning

The batch size (N = number of events per Merkle tree) directly impacts cost and latency:

| Batch Size | Merkle Tree Depth | Anchoring Frequency (at 1 event/min) | Gas Cost / Day  |
| ---------- | ----------------- | ------------------------------------ | --------------- |
| 1          | 0 (no tree)       | Every minute                         | $720–$2,880     |
| 10         | 4 levels          | Every 10 min                         | $72–$288        |
| 100        | 7 levels          | Every ~1.7 hours                     | $7–$29          |
| **1,000**  | **10 levels**     | **Every ~16.7 hours**                | **$0.70–$2.90** |

**Recommended default**: **100 events per batch** — provides a good balance between cost ($7–29/day), verification granularity (~2-hour batches), and Merkle proof depth (7 hashes).

### 8.2 Gas Optimization

Strategies to minimize on-chain costs:

1. **Single storage slot per anchor**: The `merkle_root` is exactly 32 bytes (one EVM storage slot). The `batch_id` can be derived from the event counter, avoiding extra storage.
2. **Calldata-only mode**: For even cheaper anchoring, emit the Merkle root as an event log instead of storing it in contract state. Event logs cost ~375 gas per 32 bytes vs. 20,000 gas for storage.
3. **Layer 2 anchoring**: Deploy on an L2 (Polygon, Arbitrum, Base) for 10–100x gas reduction while inheriting Ethereum's security guarantees.
4. **Batch aggregation across time**: Anchor once per day with a batch of 1,440 events for maximum cost efficiency.

### 8.3 Asynchronous Anchoring

The anchoring process runs as a **separate, non-blocking process**:

```
┌─────────────────────────────────────────────────────────┐
│ MAIN PROCESS (Real-Time)                                │
│ Sensor → AI → Risk → Fan → Event → Hash → Local Chain  │
│                                                         │
│ ▲ Never blocked by anchoring                            │
└──────────────────────────┬──────────────────────────────┘
                           │ Event queue (async)
                           ▼
┌──────────────────────────────────────────────────────────┐
│ ANCHORING PROCESS (Background)                           │
│ Collect batch → Build Merkle tree → Submit to Ethereum   │
│                                                          │
│ • Runs on separate thread/process                        │
│ • Tolerates network latency & failures                   │
│ • Retries with exponential backoff                       │
│ • Does NOT affect safety operations                      │
└──────────────────────────────────────────────────────────┘
```

### 8.4 Non-Blocking Safety Operations

The architecture guarantees that **safety control is never gated on blockchain operations**:

- If Ethereum is congested → Safety system continues, events queue for later anchoring.
- If the internet is down → Local blockchain continues recording, anchoring resumes when connectivity is restored.
- If the smart contract reverts → Safety system is unaffected, anchoring retries.
- If gas prices spike → Batch size automatically increases, anchoring continues at reduced frequency.

**The safety system is designed to be correct even if the blockchain layer fails entirely.** The blockchain adds trust, not functionality.

---

## 9. Verification Model

### How an Auditor Verifies a Safety Event

An auditor (regulator, insurer, third-party investigator) can independently verify any safety event using the following process:

#### Step 1: Obtain the Local Event

Request the raw event JSON from the operator's local storage:

```json
{
  "event_id": "evt-20260214-014518-a3f7",
  "timestamp": "2026-02-14T01:45:18.342Z",
  "tool_detected": true,
  "mq2": 387,
  "mq7": 142,
  "fan_state": "ON",
  "risk_score": 0.82,
  ...
}
```

#### Step 2: Recompute the Hash

Independently compute SHA-256 of the canonical JSON:

```
auditor_hash = SHA-256(canonical_json(event))
```

Compare with the operator's claimed `event_hash`. If they match, the event **has not been modified** since hashing.

#### Step 3: Validate Inclusion in Merkle Tree

Request the **Merkle proof** for this event from the operator:

```
Proof: [sibling_hash_1, sibling_hash_2, ..., sibling_hash_k]
Leaf position: 3 (0-indexed)
Batch ID: 42
```

Recompute the Merkle root using the proof:

```
computed_root = merkle_verify(auditor_hash, proof, leaf_position)
```

#### Step 4: Match Merkle Root with On-Chain Root

Query the Ethereum smart contract:

```solidity
(bytes32 onChainRoot, uint256 timestamp, uint256 batchId) = contract.getAnchor(42);
```

Compare `computed_root` with `onChainRoot`. If they match:

✅ The event **existed at the time of anchoring**.
✅ The event **has not been modified** since anchoring.
✅ The event **was included in the specific batch** claimed by the operator.

### Public Audit Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     PUBLIC AUDIT FLOW                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  AUDITOR                          OPERATOR          ETHEREUM     │
│  ───────                          ────────          ────────     │
│     │                                │                  │        │
│     │ 1. Request event + proof       │                  │        │
│     │ ──────────────────────────────▶│                  │        │
│     │                                │                  │        │
│     │ 2. Receive event JSON +        │                  │        │
│     │    Merkle proof + batch_id     │                  │        │
│     │ ◀──────────────────────────────│                  │        │
│     │                                │                  │        │
│     │ 3. Recompute event hash        │                  │        │
│     │    (independent, no trust)     │                  │        │
│     │                                │                  │        │
│     │ 4. Recompute Merkle root       │                  │        │
│     │    using proof                 │                  │        │
│     │                                │                  │        │
│     │ 5. Query on-chain root         │                  │        │
│     │ ──────────────────────────────────────────────────▶│       │
│     │                                │                  │        │
│     │ 6. Receive on-chain root       │                  │        │
│     │ ◀──────────────────────────────────────────────────│       │
│     │                                │                  │        │
│     │ 7. Compare computed root       │                  │        │
│     │    vs. on-chain root           │                  │        │
│     │                                │                  │        │
│     │    MATCH ──▶ ✅ VERIFIED       │                  │        │
│     │    NO MATCH ──▶ ❌ TAMPERED    │                  │        │
│     │                                │                  │        │
└──────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> The auditor needs **zero trust** in the operator. The only trusted components are: (1) the SHA-256 algorithm, (2) the Ethereum blockchain. Both are independently verifiable by anyone in the world.

---

## 10. Implementation Preparation Checklist

Before writing any code, the following decisions must be finalized:

### 10.1 Event Schema

| Decision        | Recommendation                                                                    |
| --------------- | --------------------------------------------------------------------------------- |
| Format          | JSON with canonical serialization (`sort_keys=True, separators=(',',':')`)        |
| Required fields | `event_id`, `timestamp`, `tool_detected`, `mq2`, `mq7`, `fan_state`, `risk_score` |
| Optional fields | `risk_level`, `action_taken`, `sensor_node_id`, `session_id`                      |
| Encoding        | UTF-8, no BOM                                                                     |

### 10.2 Hashing Method

| Decision  | Recommendation                      |
| --------- | ----------------------------------- |
| Algorithm | SHA-256                             |
| Library   | Python `hashlib.sha256()`           |
| Input     | Canonical JSON string (UTF-8 bytes) |
| Output    | 64-character hex string (lowercase) |

### 10.3 Block Structure

| Decision         | Recommendation                                                    |
| ---------------- | ----------------------------------------------------------------- |
| Fields           | `index`, `timestamp`, `event_hash`, `previous_hash`, `block_hash` |
| Hash computation | `SHA-256(str(index) + timestamp + event_hash + previous_hash)`    |
| Storage          | SQLite database on Raspberry Pi (`blocks.db`)                     |
| Genesis block    | Index 0, all-zero event_hash and previous_hash                    |

### 10.4 Batch Size

| Decision           | Recommendation                                |
| ------------------ | --------------------------------------------- |
| Default batch size | 100 events                                    |
| Min batch size     | 10 events (for testing)                       |
| Max batch size     | 10,000 events (for cost-critical deployments) |
| Configurable       | Yes, via environment variable `BATCH_SIZE`    |

### 10.5 Anchoring Trigger Rule

| Decision          | Recommendation                                                       |
| ----------------- | -------------------------------------------------------------------- |
| Primary trigger   | Batch full (N events accumulated)                                    |
| Secondary trigger | Time-based fallback (anchor every 24 hours regardless of batch size) |
| Failure handling  | Retry with exponential backoff (1s, 2s, 4s, ... max 5 min)           |
| Queue persistence | Unanchored batches persisted to disk, survive restarts               |

### 10.6 Smart Contract Interface

| Decision          | Recommendation                                                                |
| ----------------- | ----------------------------------------------------------------------------- |
| Network           | Ethereum Sepolia (testnet) → Ethereum Mainnet or Polygon (production)         |
| Contract language | Solidity ^0.8.19                                                              |
| Functions         | `submitAnchor(bytes32)`, `getAnchor(uint256)`, `verifyRoot(uint256, bytes32)` |
| Access control    | Single authorized submitter (Raspberry Pi's wallet address)                   |
| Deployment tool   | Hardhat or Foundry                                                            |
| Client library    | Python `web3.py`                                                              |

---

## 11. High-Level Summary

### Why This Architecture Is Powerful

This system achieves something that no traditional database can: **mathematical proof that safety records have not been tampered with**. By combining SHA-256 hashing, local block chaining, Merkle tree batching, and Ethereum anchoring, every safety event — every fan activation, every gas reading, every risk assessment — becomes a **verifiable, immutable fact** anchored to a public, decentralized ledger.

The system does not rely on trust in the operator, the system administrator, or any single entity. It relies on **cryptography and consensus** — tools that are independently verifiable by anyone with a computer.

### How It Balances Performance and Trust

The architecture is **hybrid by design**:

- **Performance**: Real-time safety control operates on the local edge device with sub-100ms latency. It never waits for network, blockchain, or consensus. The fan activates immediately when hazardous conditions are detected.
- **Trust**: The compliance layer operates asynchronously, batching events and anchoring them to Ethereum at a cadence that is economically sustainable ($7–29/day at recommended settings). Trust is added _after_ safety, not _instead of_ safety.

This separation ensures that **adding trust never compromises safety**, and **adding safety never requires trust**.

### Why It Is Review-Defensible

When facing a regulatory audit, insurance investigation, or legal challenge, this system provides:

1. **Complete event history** — Every safety event is recorded with full sensor data.
2. **Cryptographic chain of custody** — Every event is hashed and chained, making tampering detectable.
3. **Public timestamped anchor** — The Ethereum blockchain proves that the records existed at a specific point in time.
4. **Independent verifiability** — The auditor can verify everything using only public tools and standard cryptographic algorithms, without trusting the operator's systems.
5. **Proof-of-inclusion** — Any individual event can be proven to be part of a specific batch using a compact Merkle proof.

This is not security theater. This is **audit-grade, forensic-quality compliance infrastructure** — defensible in any review because it is rooted in mathematics rather than policy.

---

> _"Trust, but verify" is the philosophy of the 20th century._
> _"Don't trust — verify mathematically" is the philosophy of this system._
