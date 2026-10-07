"""Shared helpers for SCS data: tokens and PMG 0x15 (model geometry) locators.

PMG 0x15 layout used here (little endian):
  header (112 B): u8 version=0x15, 'gmP', i32 piece/part/bone/weight_width/locator counts,
                  u64 skeleton hash, f32 center[3], radius, bbox min[3], max[3],
                  i32 offsets: skeleton, parts, locators, pieces, strings, strings_size,
                               vertices, vertices_size, indices, indices_size
  part    (24 B): u64 name token, i32 piece_count, piece_idx, locator_count, locator_idx
  locator (44 B): u64 name token, f32 pos[3], f32 scale, f32 quat (w, x, y, z), i32 hookup offset
  piece  (100 B): i32 index_count, vertex_count, uv_mask, uv_channels, material, f32 center[3], radius,
                  bbox min[3], max[3], i32 stride, i32 stream offsets[8] (-1 = unused), i32 index offset
"""
import struct

ALPHABET = "\0" + "0123456789abcdefghijklmnopqrstuvwxyz_"

HEADER_OFFSETS = 72
PART_SIZE = 24
LOCATOR_SIZE = 44
PIECE_SIZE = 100
PIECE_STREAMS_AT = 64   # 8 vertex stream offsets + index offset (9 x i32) at the end of a piece
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

    def check_layout(self):
        """Assert the standard converter layout every base PMG uses:
        header | skeleton | parts | locators | pieces | strings | vertices | indices (= EOF)."""
        o = self.offsets
        expected = [
            ("parts", o["skeleton"]),   # no bones in static models: skeleton block is empty
            ("locators", o["parts"] + self.part_count * PART_SIZE),
            ("pieces", o["locators"] + self.locator_count * LOCATOR_SIZE),
            ("strings", o["pieces"] + self.piece_count * PIECE_SIZE),
            ("vertices", o["strings"] + o["strings_size"]),
            ("indices", o["vertices"] + o["vertices_size"]),
        ]
        problems = [f"{k}={o[k]} expected {v}" for k, v in expected if o[k] != v]
        if self.bone_count:
            problems.append("skinned model (bones) not supported")
        if o["indices"] + o["indices_size"] != len(self.data):
            problems.append("indices do not end the file")
        if problems:
            raise ValueError("unexpected PMG layout: " + ", ".join(problems))

    def with_locators(self, locators):
        """Return new PMG bytes with extra locators [(name, pos, quat, hookup)].

        The file is rebuilt in the standard layout (see check_layout): new locators are appended to
        the locator array, hookup strings to the string pool (padded to 4 bytes), and every absolute
        offset behind them - header offsets plus the per-piece vertex stream / index offsets - is
        shifted. Geometry bytes are copied unchanged and the indices still end the file.
        (v0.1.0-dev.1 appended the new blocks after the indices instead; the game then drew the
        locators but dropped the mesh.)
        New locators extend the last part's locator range, which must end the locator array.
        """
        self.check_layout()
        o, d = self.offsets, self.data
        last = o["parts"] + (self.part_count - 1) * PART_SIZE
        name, piece_count, piece_idx, loc_count, loc_idx = struct.unpack_from("<Q4i", d, last)
        if loc_idx + loc_count != self.locator_count:
            raise ValueError("last part does not end the locator array")

        # string pool = NUL-terminated strings, possibly zero padded; drop the padding, reuse an
        # identical string, else append
        pool = bytearray(self.strings().rstrip(b"\0"))
        if pool:
            pool += b"\0"
        new_locs = bytearray()
        for loc_name, pos, quat, hookup in locators:
            key = hookup.encode() + b"\0"
            hook = (b"\0" + pool).find(b"\0" + key)
            if hook < 0:
                hook = len(pool)
                pool += key
            new_locs += struct.pack("<Q3ff4fi", token(loc_name), *pos, 1.0, *quat, hook)
        pool += b"\0" * (-len(pool) % 4)

        loc_shift = len(new_locs)
        geo_shift = loc_shift + len(pool) - o["strings_size"]

        head = bytearray(d[:o["pieces"]]) + new_locs
        struct.pack_into("<i", head, 20, self.locator_count + len(locators))
        struct.pack_into("<4i", head, last + 8, piece_count, piece_idx, loc_count + len(locators), loc_idx)
        offsets = dict(o)
        offsets["pieces"] += loc_shift
        offsets["strings"] += loc_shift
        offsets["strings_size"] = len(pool)
        offsets["vertices"] += geo_shift
        offsets["indices"] += geo_shift
        struct.pack_into("<10i", head, HEADER_OFFSETS, *(offsets[k] for k in OFFSET_NAMES))

        pieces = bytearray(d[o["pieces"]:o["strings"]])
        for i in range(self.piece_count):
            base = i * PIECE_SIZE + PIECE_STREAMS_AT
            fields = list(struct.unpack_from("<9i", pieces, base))
            struct.pack_into("<9i", pieces, base, *(v + geo_shift if v >= 0 else v for v in fields))

        return bytes(head + pieces + pool + d[o["vertices"]:])
