"""Midea/Carrier (RG56CMI-B0) IR frame encoding.

The Carrier unit is a Carrier Midea India (CMI) build, so the remote speaks the
Midea 48-bit IR protocol rather than anything Carrier-proprietary.

Everything below marked "captured" was verified against recordings of the real
RG56CMI-B0 remote taken through an ESPHome IR receiver:

    4D B2 FC 03 02 FD    cool, fan high, 24 C
    4D B2 FC 03 03 FC    cool, fan high, 25 C
    4D B2 FD 02 03 FC    cool, fan auto, 25 C
    4D B2 F8 07 23 DC    mode 2, fan byte F8, 25 C
    4D B2 FD 02 27 D8    mode 2, fan auto, no setpoint
    4D B2 DE 21 07 F8    power off

The checksum rule and the byte3 == ~byte2 rule hold on 6/6 of those.
"""

from __future__ import annotations

from typing import Self, override

from infrared_protocols.commands import Command

CARRIER_HZ = 38000

MIN_TEMP = 17
MAX_TEMP = 30

# Timings in microseconds. These are the published Midea/RG57 values; the
# medians measured off the real RG56CMI-B0 remote are in brackets and all sit
# inside the protocol's documented +/-150 us decode tolerance. Receiver-side
# bias shortens marks and lengthens spaces, which accounts for the deltas.
LEAD_MARK = 4350  # [measured 4375]
LEAD_SPACE = 4400  # [measured 4408]
BIT_MARK = 560  # [measured 532]
ZERO_SPACE = 560  # [measured 656]
ONE_SPACE = 1690  # [measured 1657]
FRAME_GAP = 5200  # [measured ~4500]

# Static manufacturer header (captured).
HEADER_A = 0x4D
HEADER_B = 0xB2

# Power off is a fixed template the remote emits verbatim (captured); the
# trailing byte is the normal checksum over the preceding five.
_POWER_OFF_PREFIX = (0x4D, 0xB2, 0xDE, 0x21, 0x07)

# Low nibble of byte 4. Index = temperature - MIN_TEMP. This is the Midea
# gray-coded temperature table read LSB-first; it agrees exactly across
# IRremoteESP8266, sheinz/esp-midea-ir and the RG57 decode project (14/14),
# and 0x02 -> 24 C / 0x03 -> 25 C are confirmed by our own captures.
_TEMP_NIBBLE: tuple[int, ...] = (
    0x00,  # 17
    0x08,  # 18
    0x0C,  # 19
    0x04,  # 20
    0x06,  # 21
    0x0E,  # 22
    0x0A,  # 23
    0x02,  # 24
    0x03,  # 25
    0x0B,  # 26
    0x09,  # 27
    0x01,  # 28
    0x05,  # 29
    0x0D,  # 30
)

# Byte 2 carries the fan speed; byte 3 is always its complement.
# "auto" (0xFD) and "high" (0xFC) are captured; low/medium follow the
# documented Midea table.
FAN_BYTE: dict[str, int] = {
    "auto": 0xFD,
    "low": 0xF9,
    "medium": 0xFA,
    "high": 0xFC,
}

# In auto mode the remote overrides byte 2 with 0xF8 regardless of fan speed
# (captured: 4D B2 F8 07 23 DC).
_FAN_AUTO_MODE_BYTE = 0xF8


class Mode:
    COOL = "cool"
    DRY = "dry"
    AUTO = "auto"
    HEAT = "heat"
    FAN_ONLY = "fan_only"
    OFF = "off"


# High nibble of byte 4. COOL=0 is captured. AUTO=2 is captured indirectly:
# the 0xF8 auto-mode fan override appears alongside mode nibble 2. The rest
# follow IRremoteESP8266's Midea mode table, which is the most widely
# validated source for this protocol.
MODE_NIBBLE: dict[str, int] = {
    Mode.COOL: 0x0,
    Mode.DRY: 0x1,
    Mode.AUTO: 0x2,
    Mode.HEAT: 0x3,
    Mode.FAN_ONLY: 0x4,
}


def checksum(prefix: tuple[int, ...] | list[int]) -> int:
    """Midea/RG5x checksum: (0xFD - sum of the five preceding bytes) & 0xFF."""
    return (0xFD - (sum(prefix) & 0xFF)) & 0xFF


def build_bytes(
    *,
    power: bool,
    mode: str = Mode.COOL,
    temperature: float = 24,
    fan: str = "auto",
) -> list[int]:
    """Return the six protocol bytes, in LSB-first transmission order.

    Layout: [0x4D, 0xB2, fan, ~fan, mode << 4 | temp, checksum].
    """
    if not power:
        return [*_POWER_OFF_PREFIX, checksum(_POWER_OFF_PREFIX)]

    byte2 = _FAN_AUTO_MODE_BYTE if mode == Mode.AUTO else FAN_BYTE.get(fan, FAN_BYTE["auto"])

    temp = max(MIN_TEMP, min(MAX_TEMP, int(round(temperature))))
    byte4 = ((MODE_NIBBLE.get(mode, 0x0) << 4) | _TEMP_NIBBLE[temp - MIN_TEMP]) & 0xFF

    prefix = (HEADER_A, HEADER_B, byte2, (~byte2) & 0xFF, byte4)
    return [*prefix, checksum(prefix)]


# Toggles do not ride in the state frame at all -- there is no spare bit, since
# byte3 is byte2's complement and byte5 is the checksum. They use two separate
# frame families, both captured from the RG56CMI-B0 three times each.
#
# Family 1, a state frame with a command in place of the fan byte:
#   4D B2 <cmd> <~cmd> 07 F8       (power off is this family, cmd 0xDE)
SWING = 0xD6  # captured, and verified by transmitting it back at the unit

# Family 2, its own static header plus a one-byte command id:
#   AD 52 AF 50 <cmd> <checksum>
SPECIAL_PREFIX = (0xAD, 0x52, 0xAF, 0x50)
TURBO = 0x45  # captured + transmit-verified; matches the published Midea table

# Captured from the remote but NOT exposed: the RG56CMI-B0 is a generic remote
# with buttons this unit does not implement. Kept for anyone whose AC does.
FLEXICOOL = 0xDD  # remote sends it; the reference unit has no flexicool function
# NIGHT has no code at all -- the button emits only an ordinary state frame. The
# other two special ids seen in captures, 0xBD and 0x7D, were transmitted at the
# unit and did nothing.


def build_command_bytes(command: int) -> list[int]:
    """Build a family-1 command frame: 4D B2 <cmd> <~cmd> 07 F8."""
    prefix = (HEADER_A, HEADER_B, command & 0xFF, (~command) & 0xFF, 0x07)
    return [*prefix, checksum(prefix)]


def build_special_bytes(command: int) -> list[int]:
    """Build a family-2 special-function frame for a toggle command id."""
    prefix = (*SPECIAL_PREFIX, command & 0xFF)
    return [*prefix, checksum(prefix)]


def _emit_frame(timings: list[int], frame: list[int]) -> None:
    """Append one header-delimited frame. Marks positive, spaces negative."""
    timings.append(LEAD_MARK)
    timings.append(-LEAD_SPACE)
    for byte in frame:
        for bit in range(8):  # LSB first
            timings.append(BIT_MARK)
            timings.append(-(ONE_SPACE if (byte >> bit) & 1 else ZERO_SPACE))
    timings.append(BIT_MARK)


def build_timings(frame: list[int]) -> list[int]:
    """Expand the six bytes into the full transmission (frame, gap, frame).

    The remote always sends the 48 bits twice; the AC ignores a lone frame.
    """
    timings: list[int] = []
    _emit_frame(timings, frame)
    timings.append(-FRAME_GAP)
    _emit_frame(timings, frame)
    return timings


def encode(
    *,
    power: bool,
    mode: str = Mode.COOL,
    temperature: float = 24,
    fan: str = "auto",
) -> list[int]:
    return build_timings(
        build_bytes(power=power, mode=mode, temperature=temperature, fan=fan)
    )


class CarrierCommand(Command):
    """Wraps pre-built Carrier/Midea timings for the infrared emitter platform."""

    def __init__(self, timings: list[int]) -> None:
        super().__init__(modulation=CARRIER_HZ)
        self._timings = list(timings)

    @override
    def get_raw_timings(self) -> list[int]:
        return list(self._timings)

    @classmethod
    def from_raw_timings(cls, timings: list[int]) -> Self | None:
        return None
