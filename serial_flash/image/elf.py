import logging
from typing import Any, Generator, Optional, Tuple

try:
    import lief

    LIEF_AVAILABLE = True
except ImportError:
    logging.exception("`lief` is not available")
    LIEF_AVAILABLE = False


from serial_flash.execute import Info
from serial_flash.image import *

__all__ = [
    "elf",
]


def _show(s: "lief.Section"):  # type: ignore unused
    return f"{s.name}\tvaddr=[0x{s.virtual_address:08x}, 0x{s.virtual_address+s.size:08x}] sz=0x{s.size:08x}"


def elf(info: Info, filename: str) -> Optional[Image]:
    if not LIEF_AVAILABLE:
        logging.error("`lief` is not available, cannot handle ELF files")
        return None

    bin = lief.parse(filename).concrete
    if not isinstance(bin, lief.ELF.Binary):
        return None

    flash_range = mk_range(info.flash_addr, info.flash_size)

    def segments() -> Generator[Tuple[lief.ELF.Segment, lief.ELF.Section], Any, None]:
        for seg in bin.segments:
            if in_range(flash_range, mk_range(seg.physical_address, seg.physical_size)):
                for s in seg.sections:
                    # print(_show(s))
                    yield (seg, s)

    # may contain duplicates of sections if multiple segments use them. that's fine/benign
    chunks = [
        (seg.physical_address + (s.virtual_address - seg.virtual_address), s.content)
        for (seg, s) in segments()
    ]
    chunks.sort(key=lambda x: x[0])
    if not chunks:
        return None

    lo = chunks[0][0]
    hi = max(offset + mem.nbytes for (offset, mem) in chunks)
    data = bytearray(hi - lo)
    for offset, mem in chunks:
        data[offset - lo : offset - lo + mem.nbytes] = mem

    return Image(lo, data)
