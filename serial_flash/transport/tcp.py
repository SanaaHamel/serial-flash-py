import socket

import typed_argparse as tap
from typing_extensions import override

from serial_flash.transport import SocketTransport, TransportArgs


class TCP(SocketTransport):
    def __init__(self, addr: str, port: int):
        sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sk.connect((addr, port))
        super().__init__(sk)


class TcpArgs(TransportArgs):
    ip: str = tap.arg(default="192.168.4.1")
    port: int = tap.arg(default=4242)

    @override
    def transport(self):
        return TCP(self.ip, self.port)
