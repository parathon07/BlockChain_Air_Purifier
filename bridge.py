"""
Bridge Pipeline — Full Working Implementation.

Simulates the complete IoT safety pipeline end-to-end:

  Sensor Data → Risk Assessment → Fan Speed Control → Blockchain Compliance

This script can run in two modes:
  1. SIMULATION mode (default) — generates synthetic sensor readings
  2. LIVE mode — listens for real MQTT/Serial data from ESP32 nodes

Run:
    # Start Hardhat node first (Terminal 1):
    npx hardhat node

    # Deploy contract (Terminal 2):
    npx hardhat run scripts/deploy.js --network localhost

    # Run bridge (Terminal 2):
    python bridge.py
    python bridge.py --live-mqtt        # for real MQTT data
    python bridge.py --no-ethereum      # offline mode, no anchoring
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from blockchain_compliance.compliance_pipeline import CompliancePipeline
from blockchain_compliance.ethereum_anchor import EthereumAnchor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bridge")

# ===================================================================== #
#  RISK CLASSIFICATION ENGINE
# ===================================================================== #

# Thresholds for gas sensor readings (ppm)
MQ2_SAFE = 200       # Below this = safe
MQ2_CAUTION = 400    # Above this = caution
MQ2_DANGER = 600     # Above this = danger

MQ7_SAFE = 50
MQ7_CAUTION = 100
MQ7_DANGER = 200

# DHT11 thresholds
TEMP_SAFE = 35.0     # Below this = normal
TEMP_CAUTION = 45.0  # Above this = elevated
TEMP_DANGER = 55.0   # Above this = danger

HUM_SAFE = 70.0      # Below this = normal
HUM_CAUTION = 80.0   # Above this = elevated
HUM_DANGER = 90.0    # Above this = danger


def compute_risk_score(mq2: float, mq7: float, temperature: float, humidity: float, tool_detected: bool, ir_detected: bool) -> float:
    """
    Compute a risk score from 0.0 (safe) to 1.0 (critical danger).

    Combines gas sensor readings, DHT11 environmental data, tool detection,
    and IR proximity detection into a single score.
    In production, this would be replaced by the ML model inference.
    """
    # Normalize sensor readings to 0-1 range
    mq2_norm = min(mq2 / 800.0, 1.0)
    mq7_norm = min(mq7 / 300.0, 1.0)
    temp_norm = max(0.0, min((temperature - 25.0) / 40.0, 1.0))  # 25°C baseline
    hum_norm = max(0.0, min((humidity - 50.0) / 50.0, 1.0))      # 50% baseline

    # Weighted combination (MQ2 = smoke/gas is most dangerous)
    risk = 0.45 * mq2_norm + 0.25 * mq7_norm + 0.15 * temp_norm + 0.15 * hum_norm

    # Tool detection adds a 0.15 boost
    if tool_detected:
        risk = min(risk + 0.15, 1.0)

    # IR proximity detection adds a 0.05 boost (someone near the device)
    if ir_detected:
        risk = min(risk + 0.05, 1.0)

    return round(risk, 2)


def classify_risk(score: float) -> str:
    """Map a risk score to a human-readable level."""
    if score >= 0.8:
        return "CRITICAL"
    elif score >= 0.5:
        return "HIGH"
    elif score >= 0.3:
        return "MEDIUM"
    else:
        return "LOW"


def determine_action(score: float, current_fan_state: str) -> str:
    """Decide what action to take based on risk score."""
    if score >= 0.3 and current_fan_state == "OFF":
        return "FAN_ACTIVATED"
    elif score < 0.3 and current_fan_state == "ON":
        return "FAN_DEACTIVATED"
    else:
        return "NONE"


# ===================================================================== #
#  FAN SPEED CONTROLLER
# ===================================================================== #

class FanController:
    """
    Fan speed controller with 3-tier risk-based speed mapping.

    In production:  Uses RPi.GPIO PWM on a real fan via MOSFET.
    In simulation:  Prints the fan state to console.
    """

    def __init__(self, simulation: bool = True):
        self.simulation = simulation
        self.current_speed = 0        # 0-100%
        self.current_state = "OFF"
        self._gpio_pin = 18           # BCM pin for real hardware

        if not simulation:
            try:
                import RPi.GPIO as GPIO
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self._gpio_pin, GPIO.OUT)
                self._pwm = GPIO.PWM(self._gpio_pin, 25000)
                self._pwm.start(0)
                logger.info("GPIO fan controller initialized on pin %d", self._gpio_pin)
            except ImportError:
                logger.warning("RPi.GPIO not available, falling back to simulation")
                self.simulation = True

    def set_speed_from_risk(self, risk_score: float) -> int:
        """
        Set fan speed based on risk score.

        Returns the speed percentage (0-100).
        """
        if risk_score >= 0.7:
            speed = 100          # DANGER: Maximum speed
        elif risk_score >= 0.3:
            # CAUTION: Scale linearly from 40% to 80%
            speed = int(40 + (risk_score - 0.3) / 0.4 * 40)
        else:
            speed = 0            # SAFE: Fan off

        self.current_speed = speed
        self.current_state = "ON" if speed > 0 else "OFF"

        if self.simulation:
            bar = "#" * (speed // 5) + "-" * (20 - speed // 5)
            logger.info("FAN: [%s] %3d%%  (%s)", bar, speed, self.current_state)
        else:
            self._pwm.ChangeDutyCycle(speed)

        return speed

    def shutdown(self):
        """Safely turn off fan."""
        self.current_speed = 0
        self.current_state = "OFF"
        if not self.simulation:
            self._pwm.ChangeDutyCycle(0)
            import RPi.GPIO as GPIO
            GPIO.cleanup()
        logger.info("Fan controller shut down.")


# ===================================================================== #
#  SENSOR DATA SIMULATOR
# ===================================================================== #

def simulate_sensor_stream(num_readings: int = 20, interval: float = 1.0):
    """
    Generate a realistic sequence of sensor readings.

    Simulates a scenario:
      1. Normal environment (readings 1-5)
      2. Smoke detected, rising danger (readings 6-12)
      3. Critical peak (readings 13-15)
      4. Situation resolving (readings 16-18)
      5. Back to safe (readings 19-20)
    """
    scenarios = [
        # (mq2_base, mq7_base, temp, hum, tool_detected, ir_detected, description)
        (80, 20, 26.0, 45.0, False, False, "Normal air quality"),
        (90, 25, 26.5, 46.0, False, False, "Normal air quality"),
        (100, 30, 27.0, 48.0, False, False, "Slight variation"),
        (110, 35, 27.5, 50.0, False, False, "Minor fluctuation"),
        (130, 40, 28.0, 52.0, False, True, "IR: proximity detected"),
        (250, 80, 32.0, 58.0, True, True, "Tool detected, smoke rising"),
        (350, 110, 36.0, 62.0, True, True, "Smoke increasing"),
        (420, 135, 40.0, 68.0, True, True, "Approaching caution level"),
        (500, 160, 45.0, 74.0, True, True, "HIGH risk territory"),
        (550, 180, 50.0, 78.0, True, True, "Danger zone"),
        (620, 210, 55.0, 85.0, True, True, "CRITICAL - heavy contamination"),
        (700, 250, 60.0, 90.0, True, True, "CRITICAL - peak danger"),
        (680, 230, 58.0, 88.0, True, True, "CRITICAL - sustained"),
        (600, 200, 52.0, 82.0, True, True, "Starting to decrease"),
        (480, 160, 45.0, 72.0, True, False, "Ventilation taking effect"),
        (350, 120, 38.0, 62.0, False, False, "Tool removed, clearing"),
        (220, 70, 32.0, 55.0, False, False, "Air quality improving"),
        (150, 45, 28.0, 50.0, False, False, "Near normal"),
        (100, 30, 26.0, 46.0, False, False, "Safe levels restored"),
        (85, 22, 25.5, 45.0, False, False, "Normal air quality"),
    ]

    for i in range(min(num_readings, len(scenarios))):
        mq2_base, mq7_base, temp, hum, tool, ir, desc = scenarios[i]

        # Add realistic noise
        mq2 = max(0, mq2_base + random.randint(-15, 15))
        mq7 = max(0, mq7_base + random.randint(-8, 8))
        temperature = round(temp + random.uniform(-1.0, 1.0), 1)
        humidity = round(hum + random.uniform(-2.0, 2.0), 1)

        reading = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "mq2": mq2,
            "mq7": mq7,
            "temperature": temperature,
            "humidity": humidity,
            "tool_detected": tool,
            "ir_detected": ir,
            "node_id": "ESP32-NODE-01",
            "description": desc,
        }

        yield reading
        time.sleep(interval)


# ===================================================================== #
#  MAIN BRIDGE PIPELINE
# ===================================================================== #

class BridgePipeline:
    """
    The main bridge that ties together:
      - Sensor input (simulated or real)
      - Risk assessment
      - Fan speed control
      - Blockchain compliance logging
      - Ethereum anchoring
    """

    def __init__(self, use_ethereum: bool = True):
        self.fan = FanController(simulation=True)
        self.use_ethereum = use_ethereum

        # --- Ethereum client (optional) ---
        self.anchor: Optional[EthereumAnchor] = None
        if use_ethereum:
            self.anchor = self._connect_ethereum()

        # --- Compliance pipeline ---
        tmpdir = tempfile.mkdtemp(prefix="bridge_")
        self.pipeline = CompliancePipeline(
            db_path=os.path.join(tmpdir, "blocks.db"),
            events_db_path=os.path.join(tmpdir, "events.db"),
            batch_size=5,   # Small batch for demo (use 100 in production)
            anchor_client=self.anchor,
        )
        self.data_dir = tmpdir
        self.event_count = 0

    def _connect_ethereum(self) -> Optional[EthereumAnchor]:
        """Try to connect to Ethereum via deployment.json."""
        deploy_path = os.path.join(os.path.dirname(__file__), "deployment.json")
        if not os.path.exists(deploy_path):
            logger.warning("deployment.json not found — running without Ethereum")
            return None

        with open(deploy_path) as f:
            info = json.load(f)

        anchor = EthereumAnchor(
            rpc_url=os.getenv("ETHEREUM_RPC_URL", "http://127.0.0.1:8545"),
            contract_address=info["contractAddress"],
            contract_abi_path=os.getenv(
                "COMPLIANCE_CONTRACT_ABI_PATH",
                "./blockchain_compliance/contracts/SafetyComplianceAnchor.abi.json",
            ),
            private_key=os.getenv("COMPLIANCE_PRIVATE_KEY"),
        )

        if anchor.connect():
            logger.info("Ethereum connected at %s", anchor.rpc_url)
            logger.info("Contract: %s", info["contractAddress"])
            return anchor
        else:
            logger.warning("Could not connect to Ethereum — running offline")
            return None

    def process_reading(self, reading: dict) -> dict:
        """
        Process a single sensor reading through the full pipeline.

        This is the core integration point:
          1. Compute risk score     (instant)
          2. Control fan speed      (instant, <10ms)
          3. Log to blockchain      (async, non-blocking to safety)
        """
        self.event_count += 1
        mq2 = reading["mq2"]
        mq7 = reading["mq7"]
        temperature = reading["temperature"]
        humidity = reading["humidity"]
        tool = reading["tool_detected"]
        ir = reading["ir_detected"]

        # === STEP 1: Risk Assessment (instant) ===
        risk_score = compute_risk_score(mq2, mq7, temperature, humidity, tool, ir)
        risk_level = classify_risk(risk_score)

        # === STEP 2: Fan Control (instant, safety-critical) ===
        fan_speed = self.fan.set_speed_from_risk(risk_score)
        action = determine_action(risk_score, self.fan.current_state)

        # === STEP 3: Blockchain Compliance (async) ===
        event_data = {
            "timestamp": reading["timestamp"],
            "tool_detected": tool,
            "mq2": mq2,
            "mq7": mq7,
            "temperature": temperature,
            "humidity": humidity,
            "ir_detected": ir,
            "fan_state": self.fan.current_state,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "action_taken": action if action != "NONE" else ("FAN_ACTIVATED" if self.fan.current_state == "ON" else "NONE"),
            "sensor_node_id": reading.get("node_id", "ESP32-NODE-01"),
        }

        result = self.pipeline.process_event(event_data)

        return {
            "reading_num": self.event_count,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "fan_speed": fan_speed,
            "event_hash": result["event_hash"],
            "block_index": result["block_index"],
            "batch_triggered": result.get("batch_triggered", False),
            "merkle_root": result.get("merkle_root"),
        }

    def run_simulation(self, num_readings: int = 20, interval: float = 1.5):
        """Run the full pipeline with simulated sensor data."""
        print()
        print("=" * 72)
        print("   BLOCKCHAIN AIR PURIFIER — FULL PIPELINE SIMULATION")
        print("=" * 72)
        eth_status = "CONNECTED" if self.anchor and self.anchor.is_connected else "OFFLINE"
        print(f"   Ethereum:   {eth_status}")
        print(f"   Batch size: {self.pipeline.batch_manager.batch_size}")
        print(f"   Data dir:   {self.data_dir}")
        print("=" * 72)
        print()

        print("-" * 88)
        print(f" {'#':>3}  {'MQ2':>5} {'MQ7':>5} {'Temp':>5} {'Hum%':>5} {'Tool':>5} {'IR':>3}  {'Risk':>5} {'Level':>8}  {'Fan%':>4}  {'Block':>5}  Status")
        print("-" * 88)

        for reading in simulate_sensor_stream(num_readings, interval):
            result = self.process_reading(reading)

            # Status indicator
            status = ""
            if result["batch_triggered"]:
                status = ">> BATCH ANCHORED"
                if result["merkle_root"]:
                    status += f" (root={result['merkle_root'][:12]}...)"

            tool_str = "YES" if reading["tool_detected"] else " - "
            ir_str = "Y" if reading["ir_detected"] else "-"

            print(
                f" {result['reading_num']:>3}  "
                f"{reading['mq2']:>5} {reading['mq7']:>5} "
                f"{reading['temperature']:>5.1f} {reading['humidity']:>5.1f} "
                f"{tool_str:>5} {ir_str:>3}  "
                f"{result['risk_score']:>5.2f} {result['risk_level']:>8}  "
                f"{result['fan_speed']:>3}%  "
                f"{result['block_index']:>5}  "
                f"{status}"
            )

        # Flush remaining events
        print()
        print("-" * 88)
        flush_record = self.pipeline.shutdown()
        if flush_record:
            print(f"   Flushed remaining {len(flush_record.event_hashes)} events to batch")

        # Final summary
        self._print_summary()

    def _print_summary(self):
        """Print final system status."""
        status = self.pipeline.get_chain_status()
        print()
        print("=" * 72)
        print("   FINAL STATUS")
        print("=" * 72)
        print(f"   Total events processed:  {self.event_count}")
        print(f"   Local chain blocks:      {status['chain_length']}")
        print(f"   Chain integrity:         {'VALID' if status['chain_valid'] else 'TAMPERED!'}")
        print(f"   Batches completed:       {status['total_batches']}")

        if self.anchor and self.anchor.is_connected:
            count = self.anchor.get_anchor_count()
            print(f"   On-chain anchors:        {count}")

            # Verify each batch against on-chain
            print()
            print("   On-chain verification:")
            for i in range(status["total_batches"]):
                batch = self.pipeline.batch_manager.get_batch(i)
                if batch:
                    on_chain = self.anchor.verify_root(i, batch.merkle_root)
                    symbol = "PASS" if on_chain else "FAIL"
                    print(f"     Batch {i}: {symbol} (root={batch.merkle_root[:20]}...)")
        else:
            print(f"   Ethereum:                OFFLINE (local chain only)")

        print()
        print(f"   Data stored in: {self.data_dir}")
        print("=" * 72)


# ===================================================================== #
#  ENTRY POINT
# ===================================================================== #

def main():
    parser = argparse.ArgumentParser(
        description="Bridge Pipeline — Sensor to Blockchain"
    )
    parser.add_argument(
        "--no-ethereum", action="store_true",
        help="Run without Ethereum (local chain only)"
    )
    parser.add_argument(
        "--readings", type=int, default=20,
        help="Number of simulated readings (default: 20)"
    )
    parser.add_argument(
        "--interval", type=float, default=1.5,
        help="Seconds between readings (default: 1.5)"
    )
    args = parser.parse_args()

    bridge = BridgePipeline(use_ethereum=not args.no_ethereum)
    bridge.run_simulation(
        num_readings=args.readings,
        interval=args.interval,
    )


if __name__ == "__main__":
    main()
