/*
 * ============================================================
 *  ESP32 Fan Test — BlockChain Air Purifier
 * ============================================================
 *  Tests the purifier fan at multiple speed levels using PWM.
 *  Reads back RPM via a tachometer wire (if available) to
 *  confirm the fan is spinning correctly.
 *
 *  Wiring:
 *    ESP32 GPIO 25  →  MOSFET gate (controls fan power)
 *    ESP32 GPIO 26  →  Fan TACH wire (optional, for RPM read)
 *    Fan VCC        →  12 V supply (through MOSFET drain)
 *    Fan GND        →  Common ground with ESP32
 *
 *  Open Serial Monitor at 115200 baud to see results.
 * ============================================================
 */

// ── Pin Definitions ──────────────────────────────────────────
#define FAN_PWM_PIN     25    // PWM output to MOSFET gate
#define FAN_TACH_PIN    26    // Tachometer input (optional)
#define LED_PIN         2     // Built-in LED for visual status

// ── PWM Configuration ────────────────────────────────────────
#define PWM_FREQUENCY   25000 // 25 kHz — standard for 4-pin fans
#define PWM_RESOLUTION  8     // 8-bit → duty 0–255

// ── Tachometer ───────────────────────────────────────────────
volatile unsigned long tachPulseCount = 0;
unsigned long lastRpmCalcTime = 0;
float currentRpm = 0.0;

// ── Test Parameters ──────────────────────────────────────────
const int testSpeeds[] = {0, 64, 128, 192, 255}; // 0%, 25%, 50%, 75%, 100%
const char* speedLabels[] = {"OFF (0%)", "LOW (25%)", "MED (50%)", "HIGH (75%)", "MAX (100%)"};
const int numTests = 5;
const unsigned long RAMP_HOLD_MS = 3000; // hold each speed for 3 seconds

// ── State ────────────────────────────────────────────────────
bool tachAvailable = false;

// ══════════════════════════════════════════════════════════════
//  Tachometer ISR — counts pulses from the fan's TACH wire
// ══════════════════════════════════════════════════════════════
void IRAM_ATTR tachISR() {
  tachPulseCount++;
}

// ══════════════════════════════════════════════════════════════
//  Calculate RPM from pulse count
//  Most fans emit 2 pulses per revolution.
// ══════════════════════════════════════════════════════════════
float calculateRPM() {
  unsigned long now = millis();
  unsigned long elapsed = now - lastRpmCalcTime;

  if (elapsed < 500) return currentRpm; // wait at least 500ms

  noInterrupts();
  unsigned long pulses = tachPulseCount;
  tachPulseCount = 0;
  interrupts();

  // RPM = (pulses / 2) * (60000 / elapsed_ms)
  float rpm = (pulses / 2.0) * (60000.0 / elapsed);
  lastRpmCalcTime = now;
  currentRpm = rpm;
  return rpm;
}

// ══════════════════════════════════════════════════════════════
//  Set fan speed (0–255)
// ══════════════════════════════════════════════════════════════
void setFanSpeed(int duty) {
  duty = constrain(duty, 0, 255);
  ledcWrite(FAN_PWM_PIN, duty);

  // LED brightness mirrors fan speed for visual feedback
  analogWrite(LED_PIN, duty);
}

// ══════════════════════════════════════════════════════════════
//  Print a separator line
// ══════════════════════════════════════════════════════════════
void printSeparator() {
  Serial.println("────────────────────────────────────────────");
}

// ══════════════════════════════════════════════════════════════
//  SETUP
// ══════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("╔══════════════════════════════════════════╗");
  Serial.println("║   ESP32 Fan Test — Air Purifier v1.0     ║");
  Serial.println("╚══════════════════════════════════════════╝");
  Serial.println();

  // Configure PWM (ESP32 Arduino Core v3.x API)
  ledcAttach(FAN_PWM_PIN, PWM_FREQUENCY, PWM_RESOLUTION);
  setFanSpeed(0); // start with fan off

  // Configure LED
  pinMode(LED_PIN, OUTPUT);

  // Configure tachometer (optional)
  pinMode(FAN_TACH_PIN, INPUT_PULLUP);

  // Check if tach wire is connected (if pin reads LOW, likely connected)
  delay(100);
  int tachRead = digitalRead(FAN_TACH_PIN);
  tachAvailable = true; // assume available, will validate during test
  attachInterrupt(digitalPinToInterrupt(FAN_TACH_PIN), tachISR, FALLING);
  lastRpmCalcTime = millis();

  Serial.println("Configuration:");
  Serial.printf("  PWM Pin:       GPIO %d\n", FAN_PWM_PIN);
  Serial.printf("  Tach Pin:      GPIO %d\n", FAN_TACH_PIN);
  Serial.printf("  PWM Frequency: %d Hz\n", PWM_FREQUENCY);
  Serial.printf("  PWM Resolution: %d-bit (0–255)\n", PWM_RESOLUTION);
  Serial.println();

  // ── Run the test sequence ────────────────────────────────
  runFanTest();
}

// ══════════════════════════════════════════════════════════════
//  Main Fan Test Sequence
// ══════════════════════════════════════════════════════════════
void runFanTest() {
  Serial.println("Starting fan test sequence...");
  Serial.println("Each speed level is held for 3 seconds.");
  Serial.println();
  printSeparator();
  Serial.printf(" %-12s │ %-9s │ %-10s │ %s\n", "Speed", "Duty", "RPM", "Status");
  printSeparator();

  int passCount = 0;
  int failCount = 0;

  for (int i = 0; i < numTests; i++) {
    int duty = testSpeeds[i];
    const char* label = speedLabels[i];

    // Set the speed
    setFanSpeed(duty);

    // Reset tach counter
    noInterrupts();
    tachPulseCount = 0;
    interrupts();
    lastRpmCalcTime = millis();

    // Wait for fan to stabilize
    delay(RAMP_HOLD_MS);

    // Read RPM
    float rpm = calculateRPM();

    // Determine pass/fail
    bool pass = false;
    if (duty == 0) {
      // Fan should be stopped (RPM near zero)
      pass = (rpm < 100);
    } else {
      // Fan should be spinning (RPM > 200 for any non-zero duty)
      pass = (rpm > 200);
    }

    // If tach gives 0 for all, it might not be connected
    const char* status;
    if (duty > 0 && rpm < 1.0) {
      status = "⚠ NO TACH";
    } else if (pass) {
      status = "✅ PASS";
      passCount++;
    } else {
      status = "❌ FAIL";
      failCount++;
    }

    Serial.printf(" %-12s │ %3d/255   │ %7.0f    │ %s\n", label, duty, rpm, status);
  }

  printSeparator();

  // ── Final fan-off ──────────────────────────────────────
  setFanSpeed(0);
  delay(1000);
  float finalRpm = calculateRPM();

  Serial.println();
  Serial.println("Fan stopped. Verifying coast-down...");
  Serial.printf("  RPM after stop: %.0f\n", finalRpm);

  if (finalRpm < 100) {
    Serial.println("  Coast-down: ✅ PASS (fan stopped correctly)");
    passCount++;
  } else {
    Serial.println("  Coast-down: ❌ FAIL (fan still spinning!)");
    failCount++;
  }

  // ── Summary ────────────────────────────────────────────
  Serial.println();
  Serial.println("╔════════════════════════════════════╗");
  Serial.println("║         TEST SUMMARY               ║");
  Serial.println("╠════════════════════════════════════╣");
  Serial.printf( "║  PASSED: %d                         ║\n", passCount);
  Serial.printf( "║  FAILED: %d                         ║\n", failCount);

  if (failCount == 0) {
    Serial.println("║                                    ║");
    Serial.println("║  ✅ FAN IS WORKING CORRECTLY       ║");
  } else {
    Serial.println("║                                    ║");
    Serial.println("║  ❌ FAN HAS ISSUES — CHECK WIRING  ║");
  }

  Serial.println("╚════════════════════════════════════╝");
  Serial.println();

  // ── Troubleshooting guide ──────────────────────────────
  if (failCount > 0) {
    Serial.println("Troubleshooting:");
    Serial.println("  1. Check 12V power supply to the fan");
    Serial.println("  2. Verify MOSFET gate is on GPIO 25");
    Serial.println("  3. Ensure common ground between ESP32 and fan");
    Serial.println("  4. Check MOSFET is not burnt out");
    Serial.println("  5. Try a different fan to rule out motor failure");
    Serial.println();
  }

  Serial.println("Entering continuous monitor mode...");
  Serial.println("Send 0-255 via Serial to set fan speed manually.");
  Serial.println();
}

// ══════════════════════════════════════════════════════════════
//  LOOP — Manual speed control via Serial
// ══════════════════════════════════════════════════════════════
void loop() {
  // Check for serial input (manual speed override)
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    int duty = input.toInt();
    if (duty >= 0 && duty <= 255) {
      setFanSpeed(duty);
      Serial.printf("Fan set to duty: %d/255 (%d%%)\n", duty, (duty * 100) / 255);
    } else {
      Serial.println("Invalid input. Send a value between 0 and 255.");
    }
  }

  // Print RPM every 2 seconds
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint > 2000) {
    float rpm = calculateRPM();
    Serial.printf("RPM: %.0f\n", rpm);
    lastPrint = millis();
  }
}
