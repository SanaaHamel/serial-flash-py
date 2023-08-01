from dataclasses import dataclass
from typing import Optional, Tuple, Union

__all__ = [
    "guess",
    "Image",
    "in_range",
    "mk_range",
]


def mk_range(lo: int, sz: int):
    assert 0 <= sz
    return (lo, lo + sz)


def in_range(range: Tuple[int, int], addr: Union[int, Tuple[int, int]]) -> bool:
    assert range[0] <= range[1]

    if isinstance(addr, int):
        return range[0] <= addr < range[1]

    assert len(addr) == 2
    assert addr[0] <= addr[1]
    return range[0] <= addr[0] and addr[1] <= range[1]


@dataclass
class Image:
    addr: int  # >= 0
    data: bytearray


from serial_flash.execute import Info


def guess(info: Info, filename: str) -> Optional[Image]:
    from serial_flash.image.elf import elf

    if filename.endswith(".elf"):
        return elf(info, filename)
