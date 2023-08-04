import logging
import struct
import enum
from typing import Any, Generator, Optional, Tuple

from serial_flash.execute import Info
from serial_flash.image import *

__all__ = [
    "uf2",
]


class Flags(enum.Enum):
    NOT_MAIN_FLASH = 0x00000001
    FILE_CONTAINER = 0x00001000
    HAS_FAMILY_ID = 0x00002000
    HAS_MD5 = 0x00004000
    HAS_EXTENSIONS = 0x00008000


class UF2Block:
    def __init__(self, block: bytes):
        (
            magic0,
            magic1,
            self.flags,
            self.address,
            len,
            self.seq_id,
            self.seq_total,
            self.misc,
        ) = struct.unpack('<8I', block[0:32])
        assert magic0 == 0x0A324655, "bad magic #0"
        assert magic1 == 0x9E5D5157, "bad magic #1"
        assert len <= 476, "block data len must be <= 476"
        assert self.seq_id < self.seq_total, "seq-id must be < seq-total"
        self.data = block[32 : 32 + len]
        assert struct.unpack('<I', block[508:])[0] == 0x0AB16F30, "bad magic #2"


def _read_uf2(info: Info, filename: str):
    with open(filename, mode="rb") as f:
        data = f.read()
        blocks = [UF2Block(data[o : o + 512]) for o in range(0, len(data), 512)]
        blocks.sort(key=lambda x: x.seq_id)

    assert all(
        blocks[0].seq_total == b.seq_total for b in blocks
    ), "all blocks should have same `seq_total`"
    assert len({b.seq_id for b in blocks}) == len(blocks), "duplicated block IDs"

    blocks = [b for b in blocks if not (b.flags & Flags.NOT_MAIN_FLASH.value)]
    assert not any(
        b.flags & ~Flags.HAS_FAMILY_ID.value for b in blocks
    ), "unsupported flags found"

    if info.uf2_family is not None:
        assert all(
            b.misc == info.uf2_family
            for b in blocks
            if b.flags & Flags.HAS_FAMILY_ID.value
        ), "family ID mismatch"

    return blocks


def uf2(info: Info, filename: str) -> Optional[Image]:
    try:
        blocks = _read_uf2(info, filename)
    except AssertionError:  # FIXME: using `assert` is sloppy/cheating
        logging.exception("unhandled UF2")
        return None

    flash_range = mk_range(info.flash_addr, info.flash_size)

    blocks = [
        b for b in blocks if in_range(flash_range, mk_range(b.address, len(b.data)))
    ]
    if not blocks:
        return None

    lo = min(b.address for b in blocks)
    hi = max(b.address + len(b.data) for b in blocks)
    data = bytearray(hi - lo)
    for b in blocks:
        data[b.address - lo : b.address - lo + len(data)] = b.data

    return Image(lo, data)
