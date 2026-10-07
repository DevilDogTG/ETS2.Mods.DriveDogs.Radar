"""Shared helpers for SCS data: tokens and PMG 0x15 (model geometry) locators.

PMG 0x15 layout used here (little endian):
  header (112 B): u8 version=0x15, 'gmP', i32 piece/part/bone/weight_width/locator counts,
                  u64 skeleton hash, f32 center[3], radius, bbox min[3], max[3],
                  i32 offsets: skeleton, parts, locators, pieces, strings, strings_size,
                               vertices, vertices_size, indices, indices_size
  part    (24 B): u64 name token, i32 piece_count, piece_idx, locator_count, locator_idx
  locator (44 B): u64 name token, f32 pos[3], f32 scale, f32 quat (w, x, y, z), i32 hookup offset
"""
import struct

ALPHABET = "\0" + "0123456789abcdefghijklmnopqrstuvwxyz_"

HEADER_OFFSETS = 72
PART_SIZE = 24
LOCATOR_SIZE = 44
OFFSET_NAMES = ("skeleton", "parts", "locators", "pieces", "strings", "strings_size",
                "vertices", "vertices_size", "indices", "indices_size")


def token(text):
    """Encode a game token (<= 12 chars of [0-9a-z_])."""
    if len(text) > 12:
        raise ValueError(f"token too long: {text!r}")
    return sum(ALPHABET.index(ch) * 38 ** i for i, ch in enumerate(text))


def untoken(value):
    out = ""
    while value:
        value, rest = divmod(value, 38)
        out += ALPHABET[rest]
    return out


class Pmg:
    """Read-only view of a PMG 0x15 file plus a locator injector."""

    def __init__(self, data):
        if data[0] != 0x15 or data[1:4] != b"gmP":
            raise ValueError("not a PMG 0x15 file")
        self.data = bytes(data)
        (self.piece_count, self.part_count, self.bone_count,
         self.weight_width, self.locator_count) = struct.unpack_from("<5i", data, 4)
        self.center = struct.unpack_from("<3f", data, 32)
        self.radius = struct.unpack_from("<f", data, 44)[0]
        self.bbox_min = struct.unpack_from("<3f", data, 48)
        self.bbox_max = struct.unpack_from("<3f", data, 60)
        self.offsets = dict(zip(OFFSET_NAMES, struct.unpack_from("<10i", data, HEADER_OFFSETS)))

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    def strings(self):
        start = self.offsets["strings"]
        return self.data[start:start + self.offsets["strings_size"]]

    def parts(self):
        base = self.offsets["parts"]
        return [struct.unpack_from("<Q4i", self.data, base + i * PART_SIZE)
                for i in range(self.part_count)]

    def locators(self):
        """[(name, pos, scale, quat, hookup or None)]"""
        pool, base, out = self.strings(), self.offsets["locators"], []
        for i in range(self.locator_count):
            name, x, y, z, scale, qw, qx, qy, qz, hook = struct.unpack_from(
                "<Q3ff4fi", self.data, base + i * LOCATOR_SIZE)
            hookup = pool[hook:pool.index(b"\0", hook)].decode() if hook >= 0 else None
            out.append((untoken(name), (x, y, z), scale, (qw, qx, qy, qz), hookup))
        return out

    def with_locators(self, locators):
        """Return new PMG bytes with extra locators [(name, pos, quat, hookup)].

        Header offsets are absolute, so the locator array and string pool are re-emitted at EOF;
        geometry and every other offset stay untouched. New locators extend the last part's
        locator range, which must therefore end the locator array.
        """
        d = bytearray(self.data)
        last = self.offsets["parts"] + (self.part_count - 1) * PART_SIZE
        name, piece_count, piece_idx, loc_count, loc_idx = struct.unpack_from("<Q4i", d, last)
        if loc_idx + loc_count != self.locator_count:
            raise ValueError("last part does not end the locator array")

        pool = bytearray(self.strings())
        start = self.offsets["locators"]
        locs = bytearray(d[start:start + self.locator_count * LOCATOR_SIZE])
        for loc_name, pos, quat, hookup in locators:
            key = hookup.encode() + b"\0"
            hook = pool.find(key)
            if hook < 0:
                hook = len(pool)
                pool += key
            locs += struct.pack("<Q3ff4fi", token(loc_name), *pos, 1.0, *quat, hook)

        new_locs = len(d)
        d += locs
        new_pool = len(d)
        d += pool
        struct.pack_into("<i", d, 20, self.locator_count + len(locators))
        struct.pack_into("<4i", d, last + 8, piece_count, piece_idx, loc_count + len(locators), loc_idx)
        struct.pack_into("<i", d, HEADER_OFFSETS + 8, new_locs)
        struct.pack_into("<2i", d, HEADER_OFFSETS + 16, new_pool, len(pool))
        return bytes(d)
