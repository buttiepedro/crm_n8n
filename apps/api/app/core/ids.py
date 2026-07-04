"""Generación de UUID v7 (RFC 9562): ordenables por tiempo.

Python 3.12 no trae uuid7 en la stdlib; implementación propia de 15 líneas
para no sumar una dependencia.
"""

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    ts_ms = time.time_ns() // 1_000_000
    ba = bytearray(ts_ms.to_bytes(6, "big") + os.urandom(10))
    ba[6] = (ba[6] & 0x0F) | 0x70  # versión 7
    ba[8] = (ba[8] & 0x3F) | 0x80  # variante RFC 4122
    return uuid.UUID(bytes=bytes(ba))
