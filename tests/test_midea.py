"""Validate the encoder against frames captured from the real RG56CMI-B0 remote.

Run with:  python tests/test_midea.py
"""

from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "carrier_ac_ir"))

# infrared_protocols only exists inside Home Assistant; stub it so the pure
# protocol code can be exercised standalone.
if "infrared_protocols" not in sys.modules:
    pkg = types.ModuleType("infrared_protocols")
    commands = types.ModuleType("infrared_protocols.commands")

    class Command:  # noqa: D401 - minimal stand-in
        def __init__(self, *, modulation: int, repeat_count: int = 0) -> None:
            self.modulation = modulation
            self.repeat_count = repeat_count

    commands.Command = Command
    pkg.commands = commands
    sys.modules["infrared_protocols"] = pkg
    sys.modules["infrared_protocols.commands"] = commands

import midea  # noqa: E402

# (description, kwargs, expected bytes) — every entry is a real capture.
CAPTURES = [
    ("cool / fan high / 24 C", dict(power=True, mode="cool", temperature=24, fan="high"),
     [0x4D, 0xB2, 0xFC, 0x03, 0x02, 0xFD]),
    ("cool / fan high / 25 C", dict(power=True, mode="cool", temperature=25, fan="high"),
     [0x4D, 0xB2, 0xFC, 0x03, 0x03, 0xFC]),
    ("cool / fan auto / 25 C", dict(power=True, mode="cool", temperature=25, fan="auto"),
     [0x4D, 0xB2, 0xFD, 0x02, 0x03, 0xFC]),
    ("auto / 25 C (F8 override)", dict(power=True, mode="auto", temperature=25, fan="auto"),
     [0x4D, 0xB2, 0xF8, 0x07, 0x23, 0xDC]),
    ("power off", dict(power=False), [0x4D, 0xB2, 0xDE, 0x21, 0x07, 0xF8]),
]


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def decode_timings(t):
    """Decode our own output back to bytes, the way a receiver would."""
    frames = []
    i = 0
    while i < len(t) - 1:
        if t[i] > 3000 and t[i + 1] < -3000:
            i += 2
            bits = []
            while i < len(t) - 1 and 0 < t[i] < 1000 and t[i + 1] < 0:
                bits.append(1 if -t[i + 1] > 1050 else 0)
                i += 2
            if len(bits) >= 48:
                frames.append(
                    [sum(bits[k * 8 + j] << j for j in range(8)) for k in range(6)]
                )
        else:
            i += 1
    return frames


def main() -> int:
    failures = 0

    print("== byte encoding vs captured frames ==")
    for name, kwargs, expected in CAPTURES:
        got = midea.build_bytes(**kwargs)
        ok = got == expected
        failures += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<28} {hexs(got)}"
              + ("" if ok else f"   expected {hexs(expected)}"))

    print("\n== checksum + complement invariants over the whole matrix ==")
    bad = 0
    for mode in ("cool", "dry", "auto", "heat", "fan_only"):
        for temp in range(midea.MIN_TEMP, midea.MAX_TEMP + 1):
            for fan in midea.FAN_BYTE:
                b = midea.build_bytes(power=True, mode=mode, temperature=temp, fan=fan)
                if b[5] != midea.checksum(b[:5]) or b[3] != (~b[2]) & 0xFF:
                    bad += 1
    failures += bool(bad)
    print(f"  [{'PASS' if not bad else 'FAIL'}] 5 modes x 14 temps x 4 fans = 280 frames, {bad} bad")

    print("\n== temperature table is a bijection over 17-30 ==")
    nibbles = {midea.build_bytes(power=True, temperature=t)[4] & 0x0F
               for t in range(midea.MIN_TEMP, midea.MAX_TEMP + 1)}
    ok = len(nibbles) == 14
    failures += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {len(nibbles)} distinct nibbles for 14 temperatures")

    print("\n== timings round-trip (sign convention: mark +, space -) ==")
    for name, kwargs, expected in CAPTURES:
        frame = midea.build_bytes(**kwargs)
        t = midea.build_timings(frame)
        frames = decode_timings(t)
        ok = len(frames) == 2 and frames[0] == frames[1] == expected
        failures += not ok
        detail = hexs(frames[0]) if frames else "no frame decoded"
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<28} {len(frames)} frames, {detail}")

    t = midea.build_timings(midea.build_bytes(power=True))
    marks = [v for i, v in enumerate(t) if i % 2 == 0]
    spaces = [v for i, v in enumerate(t) if i % 2 == 1]
    # The gap sits between the two frames, so strict alternation is expected.
    ok = all(v > 0 for v in marks) and all(v < 0 for v in spaces)
    failures += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] all {len(marks)} marks positive, "
          f"all {len(spaces)} spaces negative  (total {len(t)} elements)")

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
