# DIN rail open NILM development platform assessment

Reviewed **2026-11-08** against the delivered Crowd Supply project, its
hardware and firmware repositories, the current CTVT/ASIC work, and the Store
and Product Lifecycle board.

## Recommendation

**Invest as an open research and development platform, not yet as a consumer
energy-monitor product.** Technical viability is high and commercial
confidence is medium. The original project proved that the modular hardware
could be manufactured and that an open continuous-sampling monitor attracted
community interest, but current demand, safety compliance, component
availability, and installation economics have not been revalidated.

The near-term product is a low-volume developer platform for metrology, power
quality, FPGA DSP, open datasets, and NILM research. A mains-connected product
or Sense-like consumer appliance is a later program with separate regulatory,
installation, enclosure, support, and model-quality gates.

## Recovered platform

The
[Crowd Supply ATM90E26 campaign](https://www.crowdsupply.com/whatnick/atm90e26-energy-monitor-kits)
funded development of open single-phase kits and the DIN rail system. The
[OpenEnergyMonitor discussion](https://community.openenergymonitor.org/t/atm90e26-based-energy-monitor-crowdfunding/4822)
records support for its continuous sampling, accuracy, open hardware, ESP8266,
ESP32, MicroPython, and emonCMS integration.

The legacy repositories form a modular stack:

| Layer | Existing evidence | Reusable value |
| --- | --- | --- |
| Aggregation | [`DIN_Rail_EnergyMonitor`](https://github.com/whatnick/DIN_Rail_EnergyMonitor) | Collects hardware and Arduino/MicroPython firmware as submodules. |
| Field/power base | [`din_power_atm90e26`](https://github.com/whatnick/din_power_atm90e26) | 90-240 VAC supply, isolated 5 V domain, three voltage samplers, eight CT inputs, backup-battery charger, and 36-pin vertical socket. |
| Control variant | [`din_power_relays`](https://github.com/whatnick/din_power_relays) | Adds four optoisolated relay-driver outputs. |
| Single-phase riser | [`din_meter_atm90e26`](https://github.com/whatnick/din_meter_atm90e26) | Two ATM90E26 devices, SPI/IRQ/test signals, PCIe-x1-shaped lower edge, and upper host connector. |
| Three-phase riser | [`din_meter_atm90e36`](https://github.com/whatnick/din_meter_atm90e36) | Two ATM90E36 devices and a shared isolated SPI interface on the same vertical concept. |
| Host/isolation | [`din_isolated_SPI`](https://github.com/whatnick/din_isolated_SPI), [`din_isolated_SPI_onion`](https://github.com/whatnick/din_isolated_SPI_onion) | Isolated SPI host boards for Wemos D1 Mini and Onion Omega. |
| Firmware | [`ATM90E26_SPI_DIN_Wemos`](https://github.com/whatnick/ATM90E26_SPI_DIN_Wemos) | Earlier dual-meter Arduino integration. |

This is a stronger starting point than a blank-sheet monitor: the mechanical
stack, analog channel density, isolation concept, firmware history, and
manufacturing experience already exist.

## Why it can support open NILM

Sense demonstrates the value of high-rate aggregate measurement and local
signal processing, but its waveform path and disaggregation stack are
proprietary. The Whatnick opportunity is a transparent and reproducible
platform rather than a feature-for-feature consumer clone:

- simultaneous voltage/current samples and calibrated raw waveform access;
- local event capture and inference without mandatory cloud upload;
- documented buses, register maps, calibration records, and timestamping;
- interchangeable metering-IC, ADC, FPGA, and ASIC vertical risers;
- open datasets with appliance-event labels and reproducible baselines;
- MQTT plus bulk waveform formats suitable for emonCMS, Python, and research;
- inspectable FPGA/ASIC arithmetic and intermediate metrology results.

The current
[CTVT PMOD](https://github.com/whatnick/ctvt-pmod) already supplies coherent
24-bit voltage/current samples from an ADS131M02. Its
[CTVT Energy DSP](https://github.com/whatnick/tt-ctvt-energy-dsp) companion
captures frames, calculates moments, RMS, active power, and energy, and has
working FPGA and Tiny Tapeout flows. The iCE40UP5K build uses about half the
device, while ECP5 is the recommended full-pipeline target. That work
substantially reduces the risk of a custom digital metrology riser.

## Required v2 architecture

```text
CTs / isolated voltage source
          |
          v
+---------------- safe field/base ----------------+
| protection | calibration ID | isolated power    |
+---------------- riser interface ----------------+
          |              |               |
          v              v               v
  metering-IC riser  simultaneous ADC  FPGA/ASIC DSP
          |              |               |
          +--------------+---------------+
                         |
              local gateway / storage
                         |
          MQTT + open waveform/event API
```

1. **Separate the safety boundary.** Start with a SELV developer base using
   isolated CTs and certified isolated AC/AC voltage transformers. Treat a
   direct-mains base as a later installer/reference design requiring creepage,
   clearance, fusing, thermal, enclosure, and regulatory review.
2. **Replace or mechanically key the PCIe-shaped connector.** The legacy
   connector carries non-PCIe analog and power signals. A v2 system must not
   be insertable into commodity PCIe equipment or accept a commodity card.
3. **Publish a riser specification.** Define pinout, analog ranges, grounding,
   isolated and non-isolated rails, clocks, SPI, interrupts, board envelope,
   insertion order, identity EEPROM, calibration storage, and test fixtures.
4. **Use simultaneous ADCs for NILM experiments.** The first waveform riser
   should target coherent multi-channel sampling in the tens of kSPS per
   channel with event-triggered buffers. Higher-rate transient capture can be
   a later riser; matching Sense's 1 MHz path is not a first-release gate.
5. **Validate digital logic in FPGA before ASIC.** Port the existing CTVT DSP
   to an ECP5-class riser, add waveform/event buffering and selected harmonic
   bins, then freeze the proven subset for Tiny Tapeout or another digital
   process. Keep precision analog conversion external to the ASIC.
6. **Keep the gateway replaceable.** Support an MCU/SBC host through a stable
   protocol rather than coupling acquisition to one Wi-Fi module.

## Viability and risks

| Dimension | Assessment | Main gate |
| --- | --- | --- |
| Technical architecture | **High** | Modernize the bus and demonstrate coherent multi-channel capture. |
| FPGA DSP | **High** | Integrate the tested CTVT RTL with buffers, timing, and the riser bus. |
| Digital ASIC | **Medium** | Prove features and resource budgets in FPGA; do not start with a mixed-signal ASIC. |
| Open NILM software | **Medium** | Build a labelled dataset and beat transparent baseline models before appliance claims. |
| Research/developer demand | **Medium** | Recruit pilot users from energy, FPGA, Tiny Tapeout, and academic communities. |
| Consumer product | **Low today** | Requires safety certification, installer channel, enclosure, support, and sustained model accuracy. |
| Direct-mains open kit | **Low today** | Safety and liability are unacceptable without a formal compliance path. |

## Stage gates

1. Recover the legacy schematics, pinout, enclosures, BOMs, firmware, and
   campaign lessons in current tools.
2. Freeze the v2 safe-base and riser specifications.
3. Demonstrate synchronized voltage plus at least four current channels,
   calibration, timestamping, and loss-detectable waveform streaming.
4. Run the FPGA metrology/event pipeline and publish reference captures.
5. Publish the local API, dataset schema, baseline NILM notebooks, and privacy
   model.
6. Place no more than ten developer units with named pilot users.
7. Review demand, support load, safety scope, and model results before any
   consumer or direct-mains product decision.

## Portfolio decision

- **Stage:** Backlog
- **Decision:** Invest
- **Approval state:** Approved for investigation and prototype planning
- **Evidence confidence:** Medium
- **Channel:** None until the prototype and safety gates pass
- **Next review:** 2027-02-08

## Lifecycle backlog

The platform work is tracked in this repository and linked to the
[Whatnick Store and Product Lifecycle project](https://github.com/users/whatnick/projects/1).

- [#1](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/1) - platform epic
- [#2](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/2) - legacy recovery and safety boundary
- [#3](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/3) - vertical-riser interface
- [#4](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/4) - simultaneous ADC riser
- [#5](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/5) - FPGA waveform/event riser
- [#6](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/6) - digital metrology ASIC riser
- [#7](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/7) - local gateway and open data pipeline
- [#8](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/8) - research pilot and NILM benchmark

