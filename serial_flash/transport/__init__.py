from abc import abstractmethod
from typing import Any

import typed_argparse as tap
from typing_extensions import Buffer


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


# FIXME: Must be a better way of compositing things cmd ln args.
class TransportArgs(tap.TypedArgs):
    filename: str = tap.arg(positional=True)

    @abstractmethod
    def transport(self) -> Transport:
        pass
