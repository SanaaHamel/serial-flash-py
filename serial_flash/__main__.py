import sys
from typing import List

import typed_argparse as tap

from serial_flash import run
from serial_flash.transport.bluetooth.spp import SppArgs
from serial_flash.transport.tcp import TcpArgs


def _run_bluetooth_spp(args: SppArgs):
    run(args)


def _run_tcp(args: TcpArgs):
    run(args)


def main(args: List[str]):
    tap.Parser(
        tap.SubParserGroup(
            tap.SubParser("bt-spp", SppArgs, help="upload using Bluetooth SPP"),
            tap.SubParser("tcp", TcpArgs, help="upload using TCP"),
        )
    ).bind(
        _run_bluetooth_spp,
        _run_tcp,
    ).run(
        args,  # HACK: `,` to force black formatting to keep `bind` args on separate lines
    )


if __name__ == "__main__":
    main(sys.argv[1:])
