#!/usr/bin/env python3
"""news-image-20261119 entry: write the day's front page to /output/entry.png.

The competition is make.fun's program/v1 harness: a Python 3.13 program at the
repository root, standard library only, no network, run twice in a fresh
container with a writable /output.  The gate reads exactly the bytes this
program writes, so the program does one job and does it defensively:

  1. read the rendered page that ships beside this file (entry.png),
  2. prove it is a whole PNG or JPEG inside the gate's limits,
  3. copy those bytes to <output>/entry.png without touching them.

Anything that would make the gate refuse the entry stops the run with a JSON
error on stderr and a non-zero exit code instead of writing a bad image.

Outside the grader, MAKEFUN_OUTPUT_DIR stands in for /output:

    mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py

Four modes share the one inspection path (inspect); only the plain run writes:

    python3 main.py                publish the page to <output>/entry.png
    python3 main.py --check-only   inspect and report, write nothing
    python3 main.py --summary      one compact JSON line, write nothing
    python3 main.py --strict       inspect with the 32 KiB floor, write nothing

The run is deterministic: the same input file always produces the same output
bytes, which is what the harness's two runs are compared on.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

MAX_BYTES = 1_048_576          # the gate: at most 1 MiB
MIN_BYTES = 32_768             # --strict: below this a news page is unreadable
MAX_SIDE = 1024                # the gate: at most 1024 by 1024 pixels
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_COLOUR_TYPES = {0, 2, 3, 4, 6}
JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
SUMMARY_FIELDS = ("format", "bytes", "width", "height", "sha256")
KNOWN_FLAGS = ("--check-only", "--summary", "--strict")


class EntryError(Exception):
    """A condition that would make the graded entry invalid."""


def output_dir() -> Path:
    """The writable directory the harness gives the run (/output by default)."""
    return Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")


def source_path() -> Path:
    """The page to publish: entry.png beside this script unless overridden."""
    override = os.environ.get("MAKEFUN_ENTRY_PNG")
    return Path(override) if override else Path(__file__).resolve().parent / "entry.png"


# ------------------------------------------------------------------ PNG


def png_info(data: bytes) -> tuple[int, int]:
    """Walk every chunk, check its CRC, and return the header's dimensions."""
    if not data.startswith(PNG_MAGIC):
        raise EntryError("not a PNG: the 8-byte signature is missing")
    pos = len(PNG_MAGIC)
    width = height = 0
    seen_ihdr = seen_idat = seen_iend = False
    while pos < len(data):
        if pos + 12 > len(data):
            raise EntryError(f"truncated PNG chunk header at byte {pos}")
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise EntryError(f"truncated {kind!r} chunk: needs {length} bytes")
        payload = data[pos + 8:pos + 8 + length]
        stored = struct.unpack(">I", data[pos + 8 + length:end])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != stored:
            raise EntryError(f"{kind.decode('latin-1', 'replace')} chunk fails its CRC")
        if not seen_ihdr:
            if kind != b"IHDR" or length != 13:
                raise EntryError("the first chunk is not a 13-byte IHDR")
            width, height = struct.unpack(">II", payload[:8])
            if payload[8] not in (1, 2, 4, 8, 16) or payload[9] not in PNG_COLOUR_TYPES:
                raise EntryError("the IHDR names an unsupported bit depth or colour type")
            if payload[10] != 0 or payload[11] != 0:
                raise EntryError("the IHDR names an unknown compression or filter method")
            if payload[12] not in (0, 1):
                raise EntryError("the IHDR names an unknown interlace method")
            seen_ihdr = True
        elif kind == b"IHDR":
            raise EntryError("a second IHDR chunk appears")
        elif kind == b"IDAT":
            seen_idat = True
        elif kind == b"IEND":
            if length != 0:
                raise EntryError("the IEND chunk carries data")
            seen_iend = True
            pos = end
            break
        pos = end
    if not seen_ihdr:
        raise EntryError("no IHDR chunk")
    if not seen_idat:
        raise EntryError("no IDAT chunk: the image has no pixel data")
    if not seen_iend:
        raise EntryError("no IEND chunk: the PNG does not end")
    if pos != len(data):
        raise EntryError(f"{len(data) - pos} trailing bytes after IEND")
    return width, height


# ------------------------------------------------------------------ JPEG


def jpeg_info(data: bytes) -> tuple[int, int]:
    """Read the frame header of a JPEG and require its end marker last."""
    if not data.startswith(JPEG_MAGIC):
        raise EntryError("not a JPEG: the SOI marker is missing")
    if not data.endswith(b"\xff\xd9"):
        raise EntryError("the JPEG does not end with its EOI marker")
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise EntryError(f"expected a JPEG marker at byte {pos}")
        marker = data[pos + 1]
        if marker == 0xD9:
            break
        if marker in (0x01,) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if marker == 0xDA:      # start of scan: the frame header came before it
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if length < 2 or pos + 2 + length > len(data):
            raise EntryError(f"truncated JPEG segment at byte {pos}")
        if marker in JPEG_SOF_MARKERS:
            if length < 7:
                raise EntryError("the JPEG frame header is too short")
            height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
            return width, height
        pos += 2 + length
    raise EntryError("the JPEG holds no frame header before its scan")


# ------------------------------------------------------------------ gate


def inspect(path: Path, *, strict: bool = False) -> dict:
    """Read the page and prove it passes every check the gate makes on bytes.

    This is the single inspection path: every mode calls it exactly once, and
    ``strict`` only adds the news-page size floor on top of the gate's limits.
    """
    try:
        data = path.read_bytes()
    except OSError as err:
        raise EntryError(f"cannot read {path}: {err.strerror or err}") from err
    size = len(data)
    if size == 0:
        raise EntryError(f"{path.name} is empty")
    if size > MAX_BYTES:
        raise EntryError(f"{path.name} is {size} bytes, over the {MAX_BYTES}-byte cap")
    if data.startswith(PNG_MAGIC):
        width, height = png_info(data)
        kind = "PNG"
    elif data.startswith(JPEG_MAGIC):
        width, height = jpeg_info(data)
        kind = "JPEG"
    else:
        raise EntryError(f"{path.name} is neither a PNG nor a JPEG")
    if width < 1 or height < 1:
        raise EntryError(f"the header gives an empty image ({width}x{height})")
    if width > MAX_SIDE or height > MAX_SIDE:
        raise EntryError(f"the image is {width}x{height}, over {MAX_SIDE} by {MAX_SIDE}")
    if strict and size < MIN_BYTES:
        raise EntryError(
            f"{path.name} is {size} bytes, under the {MIN_BYTES}-byte floor "
            f"({MIN_BYTES // 1024} KiB): too small to read as a news page"
        )
    return {
        "format": kind,
        "bytes": size,
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(data).hexdigest(),
        "data": data,
    }


def receipt(info: dict) -> dict:
    """The reportable part of a checked page: everything but its raw bytes."""
    return {key: value for key, value in info.items() if key != "data"}


def publish(info: dict, target_dir: Path) -> dict:
    """Copy the checked page's exact bytes into place; return the run's receipt."""
    payload = info["data"]
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise EntryError(f"cannot make {target_dir}: {err.strerror or err}") from err
    if not target_dir.is_dir():
        raise EntryError(f"{target_dir} is not a directory")
    target = target_dir / "entry.png"
    tmp = target_dir / ".entry.png.tmp"
    try:
        tmp.write_bytes(payload)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except OSError as err:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise EntryError(f"cannot write {target}: {err.strerror or err}") from err
    return {**receipt(info), "output": str(target)}


def parse_flags(argv: list[str]) -> dict:
    """Turn the command line into the one mode plus the strict-gate switch."""
    flags = argv[1:]
    unknown = [flag for flag in flags if flag not in KNOWN_FLAGS]
    if unknown:
        raise EntryError(
            f"unknown option(s) {', '.join(unknown)}; "
            f"expected one of {', '.join(KNOWN_FLAGS)}"
        )
    return {
        "publish": not flags,               # the bare run is the graded one
        "summary": "--summary" in flags,
        "strict": "--strict" in flags,
    }


def main(argv: list[str]) -> int:
    source = source_path()
    try:
        flags = parse_flags(argv)
        info = inspect(source, strict=flags["strict"])
        if flags["summary"]:
            report = {key: info[key] for key in SUMMARY_FIELDS}
        elif flags["publish"]:
            report = publish(info, output_dir())
        else:
            report = receipt(info)
    except EntryError as err:
        sys.stderr.write(json.dumps({"done": False, "error": str(err)}) + "\n")
        return 2
    print(json.dumps({"done": True, **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
