import socket
from abc import abstractmethod
from typing import Any, List

import typed_argparse as tap
from typing_extensions import Buffer, override


# Reliable ordered stream.
# Throws on errors. No recovery expected.
class Transport:
    def __init__(self):
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args: Any):
        if not self._closed:
            self.close()

    @abstractmethod
    def send(self, data: Buffer) -> None:
        pass

    @abstractmethod
    def recv(self, n: int) -> bytes:  # POST-CONDITION: `len(result) == n`
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class SocketTransport(Transport):
    _RECV_CHUNK = 2048

    # PRECONDITION: `socket` is a reliable stream socket
    def __init__(self, socket: socket.socket):
        super().__init__()
        self._socket = socket

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
            chunk = self._socket.recv(min(n - total, self._RECV_CHUNK))
            if not chunk:
                raise RuntimeError("socket connection broken")

            chunks.append(chunk)
            total += len(chunk)

        return b"".join(chunks)

    @override
    def close(self) -> None:
        self._socket.shutdown(socket.SHUT_RDWR)
        self._socket.close()


# FIXME: Must be a better way of compositing things cmd ln args.
class TransportArgs(tap.TypedArgs):
    filename: str = tap.arg(positional=True)

    @abstractmethod
    def transport(self) -> Transport:
        pass
