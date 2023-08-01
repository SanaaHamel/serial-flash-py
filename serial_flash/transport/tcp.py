import socket
from typing import List

import typed_argparse as tap
from typing_extensions import Buffer, override

from serial_flash.transport import *


_RECV_CHUNK = 2048


class TCP(Transport):
    def __init__(self, addr: str, port: int):
        super().__init__()

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # now connect to the web server on port 80 - the normal http port
        self._socket.connect((addr, port))

    @override
    def send(self, data: Buffer) -> None:
        total = 0
        while total < len(data):
            sent = self._socket.send(data[total:])
            if sent == 0:
                raise RuntimeError("socket connection broken")

            total = total + sent

    @override
    def recv(self, n: int):
        chunks: List[bytes] = []
        total = 0

        while total < n:
            chunk = self._socket.recv(min(n - total, _RECV_CHUNK))
            if not chunk:
                raise RuntimeError("socket connection broken")

            chunks.append(chunk)
            total += len(chunk)

        return b"".join(chunks)

    @override
    def close(self) -> None:
        self._socket.shutdown(socket.SHUT_RDWR)
        self._socket.close()


class TcpArgs(TransportArgs):
    ip: str = tap.arg(default="192.168.4.1")
    port: int = tap.arg(default=4242)

    @override
    def transport(self):
        return TCP(self.ip, self.port)
