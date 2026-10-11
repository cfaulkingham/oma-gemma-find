"""Small vector helpers. Vectors are stored L2-normalized, so dot is cosine."""

import math
import struct


def truncate_normalize(values: list[float], dim: int) -> list[float]:
    """Keep the leading dimensions and L2-normalize, including after truncation."""
    if dim < 1:
        raise ValueError("dimension")
    clipped = []
    for value in list(values)[:dim]:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("vector")
        clipped.append(number)
    if not clipped:
        raise ValueError("vector")
    norm = math.sqrt(sum(value * value for value in clipped))
    if norm == 0.0:
        raise ValueError("vector")
    return [value / norm for value in clipped]


def pack(values: list[float]) -> bytes:
    return struct.pack("<" + str(len(values)) + "f", *[float(value) for value in values])


def unpack(blob: bytes) -> list[float]:
    count = len(blob) // 4
    if count == 0 or len(blob) != count * 4:
        raise ValueError("vector")
    return list(struct.unpack("<" + str(count) + "f", blob))


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
