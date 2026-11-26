"""The app icon, drawn from the idle face. Standard library only: a small PNG encoder inside an ICO container."""
import struct
import zlib
from pathlib import Path

from . import faces

SIZES = (16, 32, 48, 64, 256)  # each is an exact multiple of the 16-pixel face, so it stays crisp


def _transparent_outside(px):
    """Indexes of black pixels connected to the border. Black pixels inside the face (the eyes) stay opaque."""
    outside, todo = set(), []
    for i in range(16):
        todo += [i, 15 * 16 + i, i * 16, i * 16 + 15]
    while todo:
        n = todo.pop()
        if n in outside or tuple(px[n]) != (0, 0, 0):
            continue
        outside.add(n)
        x, y = n % 16, n // 16
        if x > 0:
            todo.append(n - 1)
        if x < 15:
            todo.append(n + 1)
        if y > 0:
            todo.append(n - 16)
        if y < 15:
            todo.append(n + 16)
    return outside


def _png(size, px, clear):
    scale = size // 16
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type: none
        for x in range(size):
            i = (y // scale) * 16 + (x // scale)
            r, g, b = px[i]
            row += bytes((r, g, b, 0 if i in clear else 255))
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def png_images():
    """[(size, png bytes)] for every icon size."""
    px = faces.FACES["idle"][0][0]
    clear = _transparent_outside(px)
    return [(s, _png(s, px, clear)) for s in SIZES]


def ico_bytes():
    px = faces.FACES["idle"][0][0]
    clear = _transparent_outside(px)
    images = [_png(s, px, clear) for s in SIZES]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in zip(SIZES, images):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)  # 0 means 256
        offset += len(data)
    return out + b"".join(images)


def write_icon(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ico_bytes())
    return path


def bmp_ico_bytes():
    """A classic BMP-frames .ico (32 and 48 px, 32 bpp + AND mask).

    The PNG frames of ico_bytes() are what Explorer and the taskbar like, but .NET's
    System.Drawing.Icon cannot resize a PNG-compressed 256 frame (pywebview sets the window
    icon through it and crashes the whole process trying). Plain DIB frames load everywhere.
    """
    px = faces.FACES["idle"][0][0]
    clear = _transparent_outside(px)
    frames = []
    for size in (32, 48):
        scale = size // 16
        stride = ((size + 31) // 32) * 4  # AND-mask row: whole pixels rounded to 4 bytes
        xor, andm = bytearray(), bytearray()
        for y in range(size - 1, -1, -1):  # bottom-up
            row = bytearray()
            mask = bytearray(stride)
            for x in range(size):
                i = (y // scale) * 16 + (x // scale)
                r, g, b = px[i]
                on = i not in clear
                row += bytes((b, g, r, 255 if on else 0))
                if not on:
                    mask[x // 8] |= 0x80 >> (x % 8)
            xor += row
            andm += mask
        body = bytes(xor) + bytes(andm)  # DIB: full colour image first, then the full AND mask
        frames.append(bytes(struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(body), 0, 0, 0, 0)) + body)
    out = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    for size, data in zip((32, 48), frames):
        out += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(frames)


def write_bmp_icon(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bmp_ico_bytes())
    return path
