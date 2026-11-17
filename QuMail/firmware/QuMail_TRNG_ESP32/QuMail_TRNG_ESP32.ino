/*
 * ============================================================================
 * QuMail Zener-Noise Entropy Demo, ESP32 Firmware
 * v2.0.1-QUMAIL
 * ============================================================================
 *
 * Educational noise-source demonstration. This board is not QKD and is not a
 * validated TRNG.
 *
 * Hardware and protocol:
 * - Pins: Zener GPIO34, Power GPIO25, OLED SDA21/SCL22 @0x3C, LED GPIO2
 * - 115200 baud, raw binary stream via Serial.write
 * - Handshake: "TRNG_PING" -> "TRNG_READY:ZENER_TRNG_ESP32\n"
 * - STATUS / STOP / START commands, auto-stream on boot
 * - Von Neumann debiasing + adaptive DC baseline
 *
 * Loop behaviour:
 * 1. The anti-latch guard uses float variance, a sustained-low requirement,
 *    warm-up, and a 5 s cooldown. Switching Zener power on every sample blocks
 *    for ~55 ms and trips the watchdog, so the guard stays conservative.
 * 2. The scope trace reads the live ADC samples at a high rate so the wave
 *    scrolls smoothly instead of one pixel per frame.
 * 3. I2C runs at 400 kHz with a timeout, because the Adafruit library drops
 *    back to 100 kHz after each frame and a bus hiccup would stall the loop.
 * 4. Byte harvesting has a per-loop time budget so OLED and serial handling
 *    always get CPU time.
 * ============================================================================
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <esp_task_wdt.h>

#define DEVICE_ID "ZENER_TRNG_ESP32"
#define FIRMWARE_VER "2.0.1-QUMAIL"

// --- Hardware Pins ---
const uint8_t ZENER_PIN = 34;
const uint8_t POWER_PIN = 25;
const uint8_t STATUS_LED_PIN = 2;

// --- OLED Display Parameters ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_I2C_ADDR 0x3C
#define OLED_SDA 21
#define OLED_SCL 22
#define I2C_CLOCK_HZ 400000UL

// clkDuring AND clkAfter both 400 kHz (library default drops back to 100 kHz)
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET,
                         I2C_CLOCK_HZ, I2C_CLOCK_HZ);
bool oledAvailable = false;

// --- Scope ring buffer (fed by live entropy samples) ---
int16_t scopeBuf[SCREEN_WIDTH];
volatile uint8_t scopeHead = 0;       // next write index
const uint8_t SCOPE_DECIMATE = 6;     // keep 1 of every N raw samples
uint8_t scopeDecimCount = 0;

// --- Timing Constants ---
const uint32_t BAUD_RATE = 115200;
const unsigned long STREAM_INTERVAL_MS = 20;      // 50 chunks/sec
const unsigned long OLED_UPDATE_INTERVAL_MS = 66; // ~15 FPS
const unsigned long LED_INTERVAL_MS = 250;
const uint32_t WDT_TIMEOUT_SECONDS = 6;
const uint32_t HARVEST_BUDGET_US = 8000;          // max time harvesting per chunk

// --- Adaptive Noise Filter & DC Baseline Tracker ---
float dcBaseline = 2048.0f;
const float ALPHA_BASELINE = 0.005f;
const float ALPHA_VARIANCE = 1.0f / 64.0f;
float acVarianceF = 0.0f;
int dynamicAcVariance = 0;               // int mirror for STATUS / OLED

// --- Signal presence mask (display only) ---
// Pickup noise on a floating input has a low variance; real Zener noise is higher.
// Waves are strictly suppressed (flat line) when variance is outside the valid 2.90 - 6.00 range.
const float SIGNAL_MIN_VAR = 2.90f;
const float SIGNAL_MAX_VAR = 6.00f;
bool signalPresent = false;

// --- Anti-latch (conservative) ---
const float LATCH_VAR_THRESHOLD = 0.8f;          // "dead signal" level
const uint32_t LATCH_SUSTAIN_SAMPLES = 4000;     // must stay dead this long
const uint32_t LATCH_WARMUP_SAMPLES = 3000;      // ignore at startup
const unsigned long LATCH_COOLDOWN_MS = 5000;    // min gap between cycles
uint32_t lowVarianceRun = 0;
uint32_t totalSamples = 0;
unsigned long lastLatchMs = 0;

// --- Entropy Bit Accumulator ---
uint8_t bitAccumulator = 0;
uint8_t bitCount = 0;
uint8_t lastBitSample = 2; // sentinel

// --- Device Statistics ---
struct TRNGStats {
  uint32_t bytesGenerated = 0;
  uint32_t vonNeumannAccepted = 0;
  uint32_t vonNeumannDiscarded = 0;
  uint32_t latchResets = 0;
} stats;

String commandLine = "";
bool isStreaming = true;

// ============================================================================
// HARDWARE CONTROLS & ANTI-LATCH
// ============================================================================

void triggerAntiLatchCycle() {
  esp_task_wdt_reset();
  digitalWrite(POWER_PIN, LOW);
  delay(40);
  digitalWrite(POWER_PIN, HIGH);
  delay(15);
  esp_task_wdt_reset();

  stats.latchResets++;
  lastLatchMs = millis();
  lowVarianceRun = 0;
  acVarianceF = 4.0f;                    // give it room to re-learn
  dcBaseline = analogRead(ZENER_PIN);

  // Drop partial state so pre/post-reset samples never mix
  lastBitSample = 2;
  bitAccumulator = 0;
  bitCount = 0;
}

// ============================================================================
// ADAPTIVE SAMPLING & NON-BLOCKING VON NEUMANN
// ============================================================================

int sampleCleanAdc() {
  int acc = 0;
  for (int i = 0; i < 4; i++) {
    acc += analogRead(ZENER_PIN);
  }
  return acc >> 2;
}

inline void scopePush(int v) {
  if (++scopeDecimCount >= SCOPE_DECIMATE) {
    scopeDecimCount = 0;
    scopeBuf[scopeHead] = (int16_t)v;
    scopeHead = (scopeHead + 1) % SCREEN_WIDTH;
  }
}

// Returns 1/0 for a valid debiased bit, -1 if discarded / waiting
int getNextDebiasedBit() {
  int raw = sampleCleanAdc();
  totalSamples++;

  // Feed the OLED scope from the same sample (no extra ADC reads)
  scopePush(raw);

  // 1. Slow DC baseline tracker
  dcBaseline = (ALPHA_BASELINE * raw) + ((1.0f - ALPHA_BASELINE) * dcBaseline);

  // 2. AC displacement + float variance estimate (no integer truncation)
  float acDisplacement = (float)raw - dcBaseline;
  float absDisp = fabsf(acDisplacement);
  acVarianceF += (absDisp - acVarianceF) * ALPHA_VARIANCE;
  dynamicAcVariance = (int)acVarianceF;

  // Signal presence with hysteresis (drives the OLED only: 2.90 to 6.00 range)
  if (acVarianceF >= SIGNAL_MIN_VAR && acVarianceF <= SIGNAL_MAX_VAR) {
    signalPresent = true;
  } else if (acVarianceF < (SIGNAL_MIN_VAR * 0.75f) || acVarianceF > (SIGNAL_MAX_VAR + 0.5f)) {
    signalPresent = false;
  }

  // 3. Latch detection: only after warm-up, only if dead for a long run,
  //    and never more often than the cooldown allows.
  if (totalSamples > LATCH_WARMUP_SAMPLES && acVarianceF < LATCH_VAR_THRESHOLD) {
    if (++lowVarianceRun >= LATCH_SUSTAIN_SAMPLES &&
        (millis() - lastLatchMs) >= LATCH_COOLDOWN_MS) {
      triggerAntiLatchCycle();
      return -1;
    }
  } else {
    lowVarianceRun = 0;
  }

  // 4. Raw bit extraction
  uint8_t rawBit = (raw & 0x01) ^ (acDisplacement > 0 ? 1 : 0);

  // 5. Von Neumann pairwise extraction
  if (lastBitSample == 2) {
    lastBitSample = rawBit;
    return -1;
  } else {
    uint8_t bit1 = lastBitSample;
    uint8_t bit2 = rawBit;
    lastBitSample = 2;

    if (bit1 != bit2) {
      stats.vonNeumannAccepted++;
      return bit1;
    } else {
      stats.vonNeumannDiscarded++;
      return -1;
    }
  }
}

// Bounded attempts; partial bits persist in the accumulator between calls
bool harvestRandomByte(uint8_t &outByte) {
  int attempts = 0;
  while (attempts < 128) {
    attempts++;
    int bit = getNextDebiasedBit();
    if (bit >= 0) {
      bitAccumulator = (bitAccumulator << 1) | (bit & 0x01);
      bitCount++;
      if (bitCount >= 8) {
        outByte = bitAccumulator;
        bitAccumulator = 0;
        bitCount = 0;
        stats.bytesGenerated++;
        return true;
      }
    }
  }
  return false;
}

// ============================================================================
// SERIAL HANDSHAKE & COMMAND PROCESSOR
// ============================================================================

void processIncomingCommand(const String &cmd) {
  String c = cmd;
  c.trim();

  if (c.equals("TRNG_PING")) {
    Serial.print("TRNG_READY:");
    Serial.println(DEVICE_ID);
    Serial.flush();
    isStreaming = true;
  } else if (c.equals("STATUS")) {
    Serial.print("STATUS:");
    Serial.print(DEVICE_ID);
    Serial.print(",BYTES:");
    Serial.print(stats.bytesGenerated);
    Serial.print(",ACCEPTED_BITS:");
    Serial.print(stats.vonNeumannAccepted);
    Serial.print(",NOISE_VAR:");
    Serial.println(dynamicAcVariance);
    Serial.flush();
  } else if (c.equals("STOP")) {
    isStreaming = false;
  } else if (c.equals("START")) {
    isStreaming = true;
  }
}

void handleSerialCommunication() {
  while (Serial.available() > 0) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (commandLine.length() > 0) {
        processIncomingCommand(commandLine);
        commandLine = "";
      }
    } else if (commandLine.length() < 32) {
      commandLine += ch;
    }
  }
}

// ============================================================================
// OLED VISUALIZATION
// ============================================================================

void drawOledOscilloscope() {
  if (!oledAvailable) return;

  display.clearDisplay();

  // Header
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("QUMAIL TRNG");
  display.setCursor(76, 0);
  if (signalPresent) {
    display.print("VAR:");
    display.print(dynamicAcVariance);
  } else {
    display.print("OFF V:");
    display.print(dynamicAcVariance);
  }

  // Graph window
  display.drawRect(0, 10, SCREEN_WIDTH, 42, WHITE);

  if (!signalPresent) {
    // Masked: flat center line instead of pickup noise
    display.drawLine(1, 31, SCREEN_WIDTH - 2, 31, WHITE);
  } else {
    int baseInt = (int)dcBaseline;
    int yRange = max(40, (int)(acVarianceF * 3.0f));

    // Walk the ring buffer oldest -> newest
    uint8_t head = scopeHead;
    int prevY = -1;
    for (int x = 1; x < SCREEN_WIDTH - 1; x++) {
      int v = scopeBuf[(head + x) % SCREEN_WIDTH] - baseInt;
      int y = map(constrain(v, -yRange, yRange), -yRange, yRange, 50, 11);
      if (prevY >= 0) {
        display.drawLine(x - 1, prevY, x, y, WHITE);
      }
      prevY = y;
    }
  }

  // Footer
  display.setCursor(0, 55);
  display.print("OUT:");
  display.print(stats.bytesGenerated);
  display.print("B");

  display.setCursor(68, 55);
  display.print(isStreaming ? "STREAMING" : "STANDBY");

  display.display();
}

// ============================================================================
// ARDUINO SETUP & RUNTIME
// ============================================================================

void setup() {
  // 1. Power Zener circuit
  pinMode(POWER_PIN, OUTPUT);
  digitalWrite(POWER_PIN, HIGH);
  delay(60);

  // 2. Status LED
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, HIGH);

  // 3. Serial (115200, matches QuMail Desktop)
  Serial.begin(BAUD_RATE);
  delay(100);

  // 4. ADC
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  pinMode(ZENER_PIN, INPUT);

  long sum = 0;
  for (int i = 0; i < 64; i++) {
    sum += sampleCleanAdc();
    delay(2);
  }
  dcBaseline = (float)sum / 64.0f;
  acVarianceF = 4.0f;
  dynamicAcVariance = 4;
  lastLatchMs = millis();

  for (int i = 0; i < SCREEN_WIDTH; i++) {
    scopeBuf[i] = (int16_t)dcBaseline;
  }

  // 5. OLED (fast I2C + timeout so the bus can never stall the loop)
  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setClock(I2C_CLOCK_HZ);
  Wire.setTimeOut(20);

  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
    oledAvailable = true;
    display.setTextColor(WHITE);
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(18, 20);
    display.print("QUMAIL TRNG 2.0");
    display.setCursor(12, 36);
    display.print("ZENER NOISE CORE");
    display.display();
    delay(500);
  }

  // 6. Watchdog (works whether or not the core already initialised it)
  esp_task_wdt_config_t wdt_config = {
    .timeout_ms = WDT_TIMEOUT_SECONDS * 1000,
    .idle_core_mask = 0,
    .trigger_panic = true
  };
  if (esp_task_wdt_init(&wdt_config) == ESP_ERR_INVALID_STATE) {
    esp_task_wdt_reconfigure(&wdt_config);
  }
  esp_task_wdt_add(NULL);

  digitalWrite(STATUS_LED_PIN, LOW);
}

void loop() {
  esp_task_wdt_reset();

  // 1. Serial handshake / commands
  handleSerialCommunication();

  // 2. Stream binary random bytes (time-boxed so the OLED never starves)
  static unsigned long lastStream = 0;
  unsigned long now = millis();
  if (isStreaming && (now - lastStream >= STREAM_INTERVAL_MS)) {
    lastStream = now;
    uint8_t chunk[8];
    uint8_t count = 0;
    uint32_t t0 = micros();

    for (int i = 0; i < 8; i++) {
      if ((micros() - t0) > HARVEST_BUDGET_US) break;
      uint8_t b;
      if (harvestRandomByte(b)) {
        chunk[count++] = b;
      }
    }

    if (count > 0) {
      Serial.write(chunk, count);
    }
  }

  // 3. OLED oscilloscope
  static unsigned long lastOled = 0;
  now = millis();
  if (now - lastOled >= OLED_UPDATE_INTERVAL_MS) {
    lastOled = now;
    drawOledOscilloscope();
  }

  // 4. Heartbeat LED
  static unsigned long lastLed = 0;
  if (now - lastLed >= LED_INTERVAL_MS) {
    lastLed = now;
    digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN));
  }

  yield();
}
