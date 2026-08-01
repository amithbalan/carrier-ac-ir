"""Decode RG56CMI-B0 (Carrier/Midea) frames out of an ir_capture.log.

Usage: python tools/decode_captures.py <log> [ISO-timestamp-cutoff]

The remote sends the same 48 bits twice per press, so the two halves of one
capture MUST decode identically. When they don't, the signal was marginal --
move the remote to within a metre of the receiver and aim straight at it, then
re-capture. Do not trust bytes from a capture flagged MISMATCH even if the
checksum passes: a weak signal can still yield a self-consistent frame.
"""

from __future__ import annotations

import ast
import re
import sys

LINE = re.compile(r"^(\S+)\s+mod=\S+\s+n=(\d+)\s+timings=(\[.*\])\s*$")

STATE_HEADER = (0x4D, 0xB2)
SPECIAL_HEADER = (0xAD, 0x52, 0xAF, 0x50)

TEMP_NIBBLE = (0x00, 0x08, 0x0C, 0x04, 0x06, 0x0E, 0x0A, 0x02,
               0x03, 0x0B, 0x09, 0x01, 0x05, 0x0D)
TEMP_OF = {n: 17 + i for i, n in enumerate(TEMP_NIBBLE)}
FAN_OF = {0xFD: "auto", 0xF9: "low", 0xFA: "medium", 0xFC: "high",
          0xF8: "auto-mode-override"}
MODE_OF = {0x0: "cool", 0x1: "dry?", 0x2: "auto?", 0x3: "heat?", 0x4: "fan_only?"}


def checksum(b):
    return (0xFD - (sum(b[:5]) & 0xFF)) & 0xFF


def _bits(t, i):
    out = []
    while i < len(t) - 1 and 250 < t[i] < 1000 and t[i + 1] < 0:
        space = -t[i + 1]
        if space > 2800:
            break
        out.append(1 if space > 1050 else 0)
        i += 2
    return out, i


def decode(t):
    """Every header-delimited 48-bit frame in one capture, in order."""
    frames, i = [], 0
    while i < len(t) - 1:
        if 3800 < t[i] < 5400 and -5400 < t[i + 1] < -3800:
            bits, j = _bits(t, i + 2)
            if len(bits) >= 48:
                frames.append([sum(bits[k * 8 + q] << q for q in range(8))
                               for k in range(6)])
                i = j
                continue
            i += 2
        else:
            i += 1
    return frames


def describe(b):
    chk = "chk ok" if b[5] == checksum(b) else f"CHK BAD (want {checksum(b):02X})"
    if tuple(b[:4]) == SPECIAL_HEADER:
        return f"SPECIAL FUNCTION  command=0x{b[4]:02X}  [{chk}]"
    if tuple(b[:2]) != STATE_HEADER:
        return f"unknown header  [{chk}]"
    if b[2] == 0xDE and b[4] == 0x07:
        return f"POWER OFF template  [{chk}]"
    inv = "" if b[3] == (~b[2]) & 0xFF else "   b3 != ~b2 !"
    fan = FAN_OF.get(b[2], f"fan?0x{b[2]:02X}")
    mode = MODE_OF.get(b[4] >> 4, f"mode?0x{b[4] >> 4:X}")
    temp = TEMP_OF.get(b[4] & 0xF, f"NOT-A-TEMP(0x{b[4] & 0xF:X})")
    return f"{mode:<10} {str(temp):<15} fan={fan:<20} [{chk}]{inv}"


def main() -> int:
    log = sys.argv[1] if len(sys.argv) > 1 else "ir_capture.log"
    since = sys.argv[2] if len(sys.argv) > 2 else ""

    events, noise, mismatched = [], 0, 0
    for line in open(log, encoding="utf-8", errors="replace"):
        m = LINE.match(line.strip())
        if not m or m.group(1) < since:
            continue
        frames = decode(ast.literal_eval(m.group(3)))
        if not frames:
            noise += 1
            continue
        agree = len({tuple(f) for f in frames}) == 1
        mismatched += not agree
        events.append((m.group(1), frames, agree))

    print(f"captures with a decodable frame: {len(events)}   "
          f"noise/fragments skipped: {noise}   MISMATCHED halves: {mismatched}\n")

    for ts, frames, agree in events:
        flag = "" if agree else "   <-- MISMATCH, signal too weak, re-capture"
        print(f"{ts[11:23]}  {len(frames)} frame(s){flag}")
        shown = [frames[0]] if agree else frames
        for f in shown:
            print(f"    {' '.join(f'{x:02X}' for x in f)}   {describe(list(f))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
