import serial_flash.image as image
from serial_flash.execute import execute
from serial_flash.transport import TransportArgs


def run(args: TransportArgs):
    print("connecting to device...")
    with args.transport() as comm:
        execute(comm, lambda info: image.guess(info, args.filename))
