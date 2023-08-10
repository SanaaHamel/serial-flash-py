import socket

import typed_argparse as tap
from typing_extensions import override

from serial_flash.transport import SocketTransport, TransportArgs


class SPP(SocketTransport):
    def __init__(self, addr: str, channel: int):
        sk = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
        sk.connect((addr, channel))
        super().__init__(sk)


class SppArgs(TransportArgs):
    addr: str = tap.arg(help="BT address to connect to")
    channel: int = tap.arg(default=1, help="SPP channel to use")

    @override
    def transport(self):
        return SPP(self.addr, self.channel)
