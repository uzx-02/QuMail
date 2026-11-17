# QuMail TRNG Demo Report

Nov 17, 2026 · @Uzair

This ESP32 add-on is a Zener-noise hardware entropy source built to demonstrate QKD-style entropy feeding into QuMail. It does not perform quantum key distribution and is not a validated true random number generator.

## Purpose and scope

The add-on supplies physical noise to QuMail Desktop so the project can show a hardware-entropy workflow instead of relying on software randomness alone. It is a demonstration component.

- **It is:** a Zener noise source read by an ESP32 and streamed as raw bytes over USB serial.
- **It is not:** real QKD, a certified TRNG, or a replacement for the OS CSPRNG. QuMail's own integration notes describe the hardware bytes being mixed with the OS CSPRNG, so the demo adds entropy on top of the software source.
- **Firmware version covered:** 2.0.1-QUMAIL.

## Circuit mechanism

A Zener diode run in its noise region produces small, rapidly changing voltage fluctuations. The ESP32 reads that signal on an analog input and turns the fluctuations into bits. The schematic and component values are below, followed by findings from reviewing the circuit as drawn.

&#91;image: Zener diode avalanche noise entropy source schematic for ESP32\]

| Function | ESP32 pin | Notes |
| --- | --- | --- |
| Zener noise input | GPIO 34 (ADC1\_CH6) | Input-only, no internal pull-up or pull-down |
| Bias / power enable | GPIO 25 | Active HIGH; firmware can power-cycle the Zener stage |
| OLED (SSD1306 128x64) | SDA 21, SCL 22 | I2C address 0x3C, run at 400 kHz |
| Status LED | GPIO 2 | Heartbeat blink every 250 ms |

The physical switch turns the noise stage on or off. With it off, GPIO 34 is left floating and picks up ambient electrical noise instead of Zener noise.

### Components (as drawn)

| Part | Value | Role |
| --- | --- | --- |
| Supply | 12 V | Powers the noise stage |
| R1 | 10 kΩ | Feeds the Zener from the supply |
| Z1 | 12 V Zener | Noise source |
| C1 | 0.1 µF | AC-couples Zener noise to the Q1 base |
| R2 | 100 kΩ | Q1 base resistor to ground |
| Q1 | 2N3904 NPN | Amplifier |
| R3 | 1 kΩ | Collector resistor to +12 V |
| R4 | 470 Ω | Emitter resistor to ground |
| C2 | 10 µF | AC-couples the collector to the ESP32 ADC input (GPIO 34) |

Signal path: Z1 noise, through C1, into the Q1 base, amplified at the collector, through C2, to GPIO 34. A correctly biased stage like this has a gain of roughly R3 / R4 = 2, and C1 with R2 forms a high-pass corner near 16 Hz.

### Circuit findings (as drawn, to verify on the board)

These come from reviewing the schematic, not from measurements on the built circuit. Check them with a multimeter before relying on them.

1. **Z1 gets almost no current.** A 12 V Zener fed from a 12 V supply through 10 kΩ has about (12 V minus its breakdown voltage) / 10 kΩ across R1, which is at most a fraction of a milliamp. Avalanche noise needs the Zener well into breakdown. Raise the supply above the Zener voltage (for example 15 to 18 V) or use a lower-voltage Zener, aiming for roughly 1 to 5 mA through Z1.
2. **Q1 has no DC bias.** The base reaches ground through R2, and C1 blocks DC from the Zener, so the base sits near 0 V, below the roughly 0.6 V needed. Q1 stays off, the collector rests at 12 V, and Zener noise of a few millivolts is not amplified. One example fix: 47 kΩ from +12 V to the base and R2 reduced to about 10 kΩ, which gives roughly 2.5 to 3 mA in Q1 and a collector near 9 V.
3. **The ADC input has no DC bias.** C2 blocks DC, so nothing sets the voltage at GPIO 34, and negative swings cannot be read. This matches the floating, touch-sensitive behavior seen on the OLED. Bias the ADC side of C2 to about 1.65 V (for example 100 kΩ to 3.3 V and 100 kΩ to ground) and keep any signal within 0 to 3.3 V, since the collector can swing far higher once Q1 conducts.
4. **GPIO 25 and the switch are not drawn.** The firmware's anti-latch power cycle drives GPIO 25, but no connection from it appears in the schematic, so that routine has no effect on this circuit as drawn. The supply ground and the ESP32 ground must also be common.

Taken together, findings 1 to 3 mean the waves on the OLED are probably dominated by ADC noise and pickup, not amplified Zener avalanche noise. That fits the observed 1 to 2 count change when the board is touched. Measure the voltage across R1, at the Q1 base and at the Q1 collector to confirm.

## Firmware mechanism

The firmware turns each noisy ADC reading into a debiased bit, packs eight bits into a byte, and streams the bytes to the PC.

1. **Sample:** 12-bit ADC at 11 dB attenuation; each reading is the average of 4 quick conversions to reduce board noise.
2. **Track the baseline:** a slow moving average (weight 0.005) follows the DC level, so room drift does not change the result.
3. **Measure noise:** the distance from that baseline feeds a running variance estimate (weight 1/64), shown on the OLED as VAR.
4. **Extract a raw bit:** the lowest ADC bit XOR whether the reading is above the baseline.
5. **Debias:** Von Neumann pairing. Bit pairs 01 and 10 give 0 and 1; pairs 00 and 11 are discarded.
6. **Stream:** up to 8 bytes every 20 ms (about 400 bytes per second at most) as raw binary at 115200 baud, with an 8 ms time limit per chunk so the display and serial handling are never starved.

**Commands** (text, newline-terminated): `TRNG_PING` returns `TRNG_READY:ZENER_TRNG_ESP32` and starts streaming; `STATUS` returns byte count, accepted bits and noise variance; `STOP` and `START` pause and resume the stream. The stream starts automatically on boot.

**Anti-latch protection:** if the signal stays dead (variance under 0.8) for 4000 samples in a row, after a 3000-sample warm-up and at most once every 5 seconds, the firmware power-cycles the Zener stage through GPIO 25 and resets its partial state.

**Display:** a scrolling oscilloscope trace at about 15 frames per second, fed from the same samples used for entropy.

## QuMail integration

No changes are needed in QuMail Desktop. Its background watcher checks the Windows serial-port registry every 2 seconds, opens a newly appeared COM port at 115200 baud, and starts reading the raw bytes.

- The bytes go into QuMail's entropy pool, where its NIST SP 800-90B style health tests run (Shannon entropy above 7.5 bits per byte, repetition and adaptive proportion checks). All formal health testing happens on the desktop; the ESP32 does not run it.
- When the tests pass, the app shows Hardware Entropy Active and the status line `Physical Hardware TRNG (COMx) | NIST SP 800-90B PASSED`.
- ML-KEM-768 key encapsulation then uses the hardware bytes mixed with the OS CSPRNG.

The firmware keeps this contract fixed: pins, baud rate, the `TRNG_PING` handshake, raw binary output and the command set.

## Calibration and observed behavior

The OLED shows a flat line with `OFF V:<n>` when the input looks like pickup noise, and a live wave with `VAR:<n>` when real signal is present. This mask affects the display only; it never changes the serial stream. It is set by `SIGNAL_MIN_VAR = 3.0`, with hysteresis so the display does not flicker (it drops back to flat below about 2.1).

| Condition | Displayed VAR |
| --- | --- |
| Switch off, hands away | 2 |
| Switch off, hands on keyboard | 1 |
| Switch on, hands away | 3 to 4 (clean wave) |
| Switch on, hands on keyboard | 1 to 2 (wave disappears) |

The margin between on and off is only about 1 to 2 counts, and touching the keyboard or board shifts the reading enough to erase it. For demonstrations, keep hands off the board and keyboard while the circuit is running.

## Limitations and recommended enhancements

The device is suitable for demonstrating a hardware-entropy workflow. These points must be addressed before calling it a dependable hardware entropy source.

**Known limitations**

- **Weak, touch-sensitive signal:** the on/off difference is about 1 to 2 ADC counts, so ambient pickup contributes to the output, and the schematic suggests the Zener signal is barely amplified (see Circuit findings).
- **Stream continues with no signal:** with the circuit off, bytes made from pickup noise are still sent, and QuMail may still report Hardware Entropy Active.
- **Correlated raw bits:** the raw bit comes from ADC samples that are not guaranteed independent, while Von Neumann debiasing assumes independent bits.
- **No on-device health tests:** continuous testing exists only in QuMail Desktop.
- **Mixed serial channel:** `STATUS` replies are text sent on the same port as the binary stream.

**Recommended enhancements**

1. Fix the circuit findings above: give Z1 real breakdown current, bias Q1 so it amplifies, and bias the GPIO 34 input to about 1.65 V.
2. Shield the noise stage and keep it away from the Wi-Fi antenna and USB lines.
3. Pause the stream when `signalPresent` is false, so only real signal is ever sent.
4. Condition the output with a cryptographic hash (for example SHA-256) over many samples before sending.
5. Add on-device repetition-count and adaptive-proportion tests with a fail-safe that stops the stream.
6. Characterize the source offline (min-entropy estimate over a long capture) before making any quality claim.

**Suggested wording for the project:** the ESP32 Zener noise board is a demonstration hardware entropy source for QKD-style workflows. It is not real QKD and not a validated TRNG, and it needs further hardening to serve as production-grade hardware entropy.
