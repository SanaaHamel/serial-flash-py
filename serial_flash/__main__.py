import typed_argparse as tap

from serial_flash import run
from serial_flash.transport.tcp import TcpArgs


def _run_tcp(args: TcpArgs):
    run(args)


def main():
    tap.Parser(
        tap.SubParserGroup(
            tap.SubParser("tcp", TcpArgs, help="upload over TCP"),
        )
    ).bind(
        _run_tcp,
    ).run()


if __name__ == "__main__":
    main()
