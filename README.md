# Carrier AC (IR)

[![hacs][hacs-badge]][hacs-url]
[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.][my-badge]][my-url]

Controls an IR-driven Carrier air conditioner from Home Assistant, presented as
its own device and integration rather than an entity buried under the IR blaster
that drives it.

Carrier's Indian units are built by **Carrier Midea India** — the `CMI` in the
`RG56CMI-B0` remote — so they speak the **Midea 48-bit IR protocol**, not
anything Carrier-proprietary. This integration builds that frame in Python and
sends it through any IR emitter exposed by the `infrared` integration, so it
does not depend on a vendor-specific climate platform on the blaster.

## Requirements

An IR emitter entity — anything in the `infrared` domain with
`device_class: emitter`. The reference setup is an ESPHome IR blaster:

```yaml
remote_transmitter:
  - id: ir_tx
    pin: P26
    carrier_duty_percent: 50%

infrared:
  - platform: ir_rf_proxy
    name: IR Transmitter
    remote_transmitter_id: ir_tx
```

The blaster needs no `climate:` block — the frame is generated here.

## Installation

**HACS** — [click here][my-url], or add this repository as a custom repository
with category `Integration`, install, then restart Home Assistant.

**Manual** — copy `custom_components/carrier_ac_ir` into your `config` directory
and restart Home Assistant.

Then add the integration from **Settings → Devices & Services → Add
Integration → Carrier AC (IR)** and pick your emitter.

## Features

| | |
|---|---|
| HVAC modes | `off`, `cool`, `dry`, `auto`, `heat`, `fan_only` |
| Target temperature | 17–30 °C, 1° steps |
| Fan modes | `auto`, `low`, `medium`, `high` |
| Current temperature | optional, from any temperature sensor you pick |
| State | restored across Home Assistant restarts |

Because IR is one-way, the entity is `assumed_state`: Home Assistant shows what
it last transmitted, which is not proof the AC acted on it. Selecting a room
temperature sensor only populates `current_temperature` for display — the unit
still regulates against its own internal sensor.

## Protocol

Every transmission carries the complete state (mode, temperature, fan), so any
single change re-sends everything. The frame is six bytes, sent LSB-first,
twice per press:

```
[0x4D] [0xB2] [fan] [~fan] [mode << 4 | temp] [checksum]
```

* **Checksum** — `(0xFD - sum(bytes 0..4)) & 0xFF`
* **Temperature** — gray-coded nibble table, 17 °C → `0x0` … 30 °C → `0xD`
* **Fan** — `auto 0xFD`, `low 0xF9`, `medium 0xFA`, `high 0xFC`; in `auto`
  mode the remote overrides this byte with `0xF8`
* **Power off** — the fixed template `4D B2 DE 21 07 F8`

Timings (µs), 38 kHz carrier: lead `4350` mark / `4400` space, bit mark `560`,
zero space `560`, one space `1690`, inter-frame gap `5200`.

`tests/test_midea.py` checks the encoder against frames recorded from a real
RG56CMI-B0 remote and runs in CI. Reproduce or extend the captures with any
`infrared` receiver entity.

### Verified vs. inferred

Captured from the physical remote and reproduced byte-for-byte by the encoder:
the header, the checksum rule, `byte3 == ~byte2`, the power-off template, fan
`auto`/`high`, mode nibble `0` (cool) and `2`, and temperatures 24 °C/25 °C.

Taken from the published Midea tables and cross-checked across
[IRremoteESP8266][ir-esp], [esp-midea-ir][esp-midea] and the [RG57 decode
project][rg57] (all three agree): the full 14-entry temperature table, fan
`low`/`medium`, and the `dry`/`heat`/`fan_only` mode nibbles.

If a mode misbehaves on your unit, capture that button and open an issue with
the decoded bytes.

## Credits

Protocol references: [IRremoteESP8266][ir-esp], [esp-midea-ir][esp-midea],
[Midea-AC-IR-Protocol-Decode][rg57], and Matthew Petroff's
[remote teardown][mpetroff].

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[my-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[my-url]: https://my.home-assistant.io/redirect/hacs_repository/?owner=amithbalan&repository=carrier-ac-ir&category=integration
[ir-esp]: https://github.com/crankyoldgit/IRremoteESP8266
[esp-midea]: https://github.com/sheinz/esp-midea-ir
[rg57]: https://github.com/smruchira/Midea-AC-IR-Protocol-Decode
[mpetroff]: https://mpetroff.net/2015/07/decoding-a-midea-air-conditioner-remote/
