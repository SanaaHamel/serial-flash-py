import math
import zlib
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from tqdm import tqdm
from typing_extensions import Buffer

from serial_flash.image import Image, in_range, mk_range
from serial_flash.transport import Transport


class Cmd:
    def __init__(self, cmd: bytes):
        assert len(cmd) == 4
        self._payload = bytearray()
        self.data(cmd)

    def u4(self, n: int):
        assert 0 <= n
        return self.data(n.to_bytes(4, "little", signed=False))

    def data(self, xs: Buffer):
        self._payload += xs
        return self

    def finish(self) -> Buffer:
        return self._payload


class _Read:
    def __init__(
        self, comm: Transport, sz: int = 0, expected_response: Optional[bytes] = b"OKOK"
    ):
        self.response = comm.recv(4)
        if expected_response is not None and self.response != expected_response:
            raise RuntimeError(f"unexpected response: {self.response}")

        self.remaining = comm.recv(sz)

    def u4(self):
        return self._consume(False, 4)

    def _consume(self, signed: bool, sz: int) -> int:
        if len(self.remaining) < sz:
            raise RuntimeError("insufficient data remaining")

        head = self.remaining[0:sz]
        self.remaining = self.remaining[sz:]
        return int.from_bytes(head, "little", signed=signed)


@dataclass
class Info:
    uf2_family: Optional[int]
    flash_addr: int
    flash_size: int
    erase_size: int
    write_size: int
    max_data_len: int


def _crc(data: Buffer):
    return zlib.crc32(data) & 0xFFFFFFFF


def _align(addr: int, alignment: int):
    assert 0 < alignment
    assert 0 <= addr
    return (addr + alignment - 1) & ~(alignment - 1)


def _cmd_sync(comm: Transport):
    comm.send(Cmd(b"SYNC").finish())
    return _Read(comm, 0, None).response


def _cmd_info(comm: Transport):
    comm.send(Cmd(b"INFO").finish())
    read = _Read(comm, 4 * 5)
    return Info(None, read.u4(), read.u4(), read.u4(), read.u4(), read.u4())


def _cmd_info_boot(comm: Transport):
    comm.send(Cmd(b"BTIF").finish())
    read = _Read(comm, 4 * 6)
    return Info(read.u4(), read.u4(), read.u4(), read.u4(), read.u4(), read.u4())


def _cmd_erase(comm: Transport, addr: int, size: int):
    assert 0 <= addr
    assert 0 <= size
    comm.send(Cmd(b"ERAS").u4(addr).u4(size).finish())
    _Read(comm)


def _cmd_erase_boot(comm: Transport, addr: int, size: int):
    assert 0 <= addr
    assert 0 <= size
    comm.send(Cmd(b"BTER").u4(addr).u4(size).finish())
    _Read(comm)


def _cmd_write(comm: Transport, addr: int, data: Buffer):
    assert 0 <= addr
    comm.send(Cmd(b"WRIT").u4(addr).u4(len(data)).data(data).finish())
    crc = _Read(comm, 4).u4()
    if crc != _crc(data):
        raise RuntimeError(f"crc mismatch: got=0x{crc:08x} expected=0x{_crc(data):08x}")


def _cmd_erase_write_ex(
    code: bytes, comm: Transport, addr: int, data: Buffer, *, detailed: bool = False
):
    assert 0 <= addr
    comm.send(
        Cmd(code).u4(addr).u4(len(data)).u4(1 if detailed else 0).data(data).finish()
    )
    read = _Read(comm, 4 * 2)
    crc = read.u4()
    changed = read.u4()
    if crc != _crc(data):
        raise RuntimeError(f"crc mismatch: got=0x{crc:08x} expected=0x{_crc(data):08x}")
    return changed


def _cmd_erase_write(
    comm: Transport, addr: int, data: Buffer, *, detailed: bool = False
):
    return _cmd_erase_write_ex(b"ERWR", comm, addr, data, detailed=detailed)


def _cmd_erase_write_boot(
    comm: Transport, addr: int, data: Buffer, *, detailed: bool = False
):
    return _cmd_erase_write_ex(b"BTEW", comm, addr, data, detailed=detailed)


def _cmd_seal(comm: Transport, img: Image):
    assert 0 <= img.addr
    comm.send(Cmd(b"SEAL").u4(img.addr).u4(len(img.data)).u4(_crc(img.data)).finish())
    _Read(comm)


def _cmd_reboot(comm: Transport, *, to_bootloader: bool = False):
    comm.send(Cmd(b"BOOT").u4(1 if to_bootloader else 0).finish())
    _Read(comm)


def _cmd_launch(comm: Transport, img: Image):  # type: ignore unused
    comm.send(Cmd(b"GOGO").u4(img.addr).finish())
    _Read(comm)


def _cmd_crc(comm: Transport, addr: int, n: int):  # type: ignore unused
    assert 0 <= addr
    assert 0 <= n
    comm.send(Cmd(b"CRCC").u4(addr).u4(n).finish())
    return _Read(comm, 4).u4()


def _execute(
    comm: Transport,
    load_img: Callable[[Info], Optional[Image]],
    *,
    classic_api: bool = False,
    update_bootloader: bool = False,
    family_override: Optional[int] = None,
) -> Optional[Tuple[Image, Optional[int]]]:
    assert not (
        update_bootloader and classic_api
    ), "can't update bootloader w/ classic API"

    print("requesting device info...")
    if update_bootloader:
        info = _cmd_info_boot(comm)
    else:
        info = _cmd_info(comm)

    if family_override is not None:
        info.uf2_family = family_override

    img = load_img(info)
    if img is None:
        # failed to load img for whatever reason, callback is responsible for logging
        return None

    def pad_len(align: int):
        return _align(len(img.data), align) - len(img.data)

    img.data += bytearray(pad_len(info.write_size))
    print(f"img size: {len(img.data)}")

    flash_span = mk_range(info.flash_addr, info.flash_size)
    img_span = mk_range(img.addr, len(img.data))
    if not in_range(flash_span, img_span):
        raise RuntimeError(
            f"can't flash image: image span is not contained by storage span. "
            f"storage=[0x{info.flash_addr:08x}, 0x{info.flash_addr+info.flash_size:08x}]; "
            f"image (padded)=[0x{img.addr:08x}, 0x{img.addr + len(img.data):08x}]"
        )

    def tqdm_chunks(desc: str, step: int, padding: int = 0):
        assert 0 <= step
        assert 0 <= padding
        with tqdm(
            desc=desc,
            total=len(img.data) + padding,
            unit="b",
            unit_scale=True,
            unit_divisor=1024,
        ) as t:
            for offset in range(0, t.total, step):
                t.update(min(step, t.total - t.n))
                yield (img.addr + offset, offset, min(len(img.data), offset + step))

    if classic_api:
        fine_grain_erase = False
        if fine_grain_erase:
            for addr, _, _ in tqdm_chunks(
                "erasing", info.erase_size, pad_len(info.erase_size)
            ):
                _cmd_erase(comm, addr, info.erase_size)
        else:
            # erase the whole thing. let the controller wear level as best it can.
            print(
                f"erasing [0x{info.flash_addr:08x}, 0x{info.flash_addr+info.flash_size:08x}]..."
            )
            _cmd_erase(comm, info.flash_addr, info.flash_size)

        info.max_data_len = 1024
        for addr, bgn, end in tqdm_chunks("writing", info.max_data_len):
            _cmd_write(comm, addr, img.data[bgn:end])
    else:
        cmd_erase = _cmd_erase_boot if update_bootloader else _cmd_erase
        cmd_update = _cmd_erase_write_boot if update_bootloader else _cmd_erase_write

        # add extra padding for flash erase
        img.data += bytearray(pad_len(info.erase_size))

        # must be aligned to maximum of write and erase alignments
        chunk_size = info.max_data_len - info.max_data_len % max(
            info.write_size, info.erase_size
        )
        # print(f"chunk size: 0x{chunk_size:x}")
        assert (
            0 < chunk_size
        ), f"controller misconfigured? unable to satisfy alignment requirements\n{info}"

        detailed = True
        change_total = math.ceil(len(img.data) / (1 if detailed else chunk_size))
        change = 0
        for addr, bgn, end in tqdm_chunks("updating", chunk_size):
            change += cmd_update(comm, addr, img.data[bgn:end], detailed=detailed)

        print(
            f"update modified {change} of {change_total} {'bytes' if detailed else 'chunks'} ({change/change_total*100:.2f}%)"
        )

    return img, info.uf2_family


def execute(comm: Transport, load_img: Callable[[Info], Optional[Image]]):
    print("sync w/ device...")

    sync_response = _cmd_sync(comm)
    classic_api = sync_response == b"WOTA"
    if sync_response not in {b"WOTA", b"WoTa"}:
        raise RuntimeError(f"unrecognised response code: {sync_response}")

    family: Optional[int] = None  # only known by fetching bootloader info
    if not classic_api:
        print("trying to update bootloader...")
        result = _execute(comm, load_img, update_bootloader=True)
        if result is None:
            print("no bootloader found in image.")
        else:
            _, family = result

    print("updating main image...")
    result = _execute(comm, load_img, classic_api=classic_api, family_override=family)
    if result is not None:
        print("finalising...")
        img, _ = result
        _cmd_seal(comm, img)
    else:
        print("no main image found? odd.")

    print("rebooting...")
    _cmd_reboot(comm)
