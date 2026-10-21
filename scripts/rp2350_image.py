#!/usr/bin/env python3
"""
RP2350 image tools: a minimal ELF32 reader, the ELF -> UF2 conversion for a RAM-only image,
and a parser for the bootrom's IMAGE_DEF block. No external dependencies.

Sources:
  UF2 block layout and magic numbers: Pico SDK src/common/boot_uf2_headers/include/boot/uf2.h
    (commit 079c6f3); family IDs: RP2350 datasheet Table 469 (5.5.3); constraints for a RAM
    image (payload 256 B, targets in 0x20000000-0x20082000, byte alignment allowed): 5.5.2.
  IMAGE_DEF block format: datasheet 5.9.1 (blocks), 5.9.3 (items), 5.9.5 (minimum image);
    constants from SDK src/common/boot_picobin_headers/include/boot/picobin.h.

  python scripts/rp2350_image.py --elf build/cells/<cell>/firmware.elf --uf2 out.uf2 --family 0xe48bff59
  python scripts/rp2350_image.py --elf build/cells/<cell>/firmware.elf          # print the IMAGE_DEF
"""

import argparse
import struct
from pathlib import Path

# ---- UF2 (SDK boot/uf2.h) ------------------------------------------------------------
UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_FLAG_FAMILY_ID_PRESENT = 0x00002000
UF2_PAYLOAD = 256                      # datasheet 5.5.2: "A payload_size of 256"

# ---- picobin (SDK boot/picobin.h) ----------------------------------------------------
BLOCK_MARKER_START = 0xFFFFDED3
BLOCK_MARKER_END = 0xAB123579
ITEM_NAMES = {0x42: "IMAGE_TYPE", 0x03: "VECTOR_TABLE", 0x44: "ENTRY_POINT", 0xFF: "LAST"}

SHF_ALLOC, SHF_EXECINSTR = 0x2, 0x4
PT_LOAD = 1


class Elf:
    """Little-endian ELF32: sections, PT_LOAD segments, symbols."""

    def __init__(self, path):
        self.data = Path(path).read_bytes()
        d = self.data
        if d[:4] != b"\x7fELF" or d[4] != 1 or d[5] != 1:
            raise ValueError(f"{path}: not a little-endian ELF32 file")
        (self.e_type, self.e_machine, _, self.entry, phoff, shoff, self.flags, _, phentsize, phnum,
         shentsize, shnum, shstrndx) = struct.unpack_from("<HHIIIIIHHHHHH", d, 16)
        self.segments = []
        for i in range(phnum):
            p_type, off, vaddr, paddr, filesz, memsz, flags, align = struct.unpack_from("<8I", d, phoff + i * phentsize)
            self.segments.append({"type": p_type, "offset": off, "vaddr": vaddr, "paddr": paddr,
                                  "filesz": filesz, "memsz": memsz, "flags": flags})
        raw = [struct.unpack_from("<10I", d, shoff + i * shentsize) for i in range(shnum)]
        strtab = raw[shstrndx]
        name = lambda off, tab: d[tab[4] + off:d.index(b"\0", tab[4] + off)].decode()  # noqa: E731
        self.sections = [{"name": name(r[0], strtab), "type": r[1], "flags": r[2], "addr": r[3], "offset": r[4],
                          "size": r[5], "link": r[6]} for r in raw]
        self.symbols = {}
        for s in self.sections:
            if s["type"] == 2:  # SHT_SYMTAB
                st = raw[s["link"]]
                for i in range(s["size"] // 16):
                    n, value, size, info, other, shndx = struct.unpack_from("<IIIBBH", d, s["offset"] + i * 16)
                    if n:
                        self.symbols[name(n, st)] = value

    def load_segments(self):
        """PT_LOAD segments with file contents, as (load address, bytes)."""
        return [(p["paddr"], self.data[p["offset"]:p["offset"] + p["filesz"]])
                for p in self.segments if p["type"] == PT_LOAD and p["filesz"]]

    def alloc_sections(self):
        """Sections that occupy target memory: (name, run address, load address, size, flags)."""
        out = []
        for s in self.sections:
            if not s["flags"] & SHF_ALLOC or s["size"] == 0:
                continue
            lma = s["addr"]
            for p in self.segments:
                if p["type"] == PT_LOAD and p["vaddr"] <= s["addr"] < p["vaddr"] + max(p["memsz"], 1):
                    lma = p["paddr"] + (s["addr"] - p["vaddr"])
                    break
            out.append((s["name"], s["addr"], lma, s["size"], s["flags"]))
        return out

    def flat_image(self):
        """(base address, bytes): every loaded byte at its load address, gaps zero-filled."""
        segs = self.load_segments()
        lo = min(a for a, _ in segs)
        hi = max(a + len(b) for a, b in segs)
        img = bytearray(hi - lo)
        for a, b in segs:
            img[a - lo:a - lo + len(b)] = b
        return lo, bytes(img)


def uf2_blocks(elf_path, family_id):
    """UF2 blocks (bytes) for the loaded contents of the ELF, 256-byte payloads from the
    lowest load address. Gaps between segments are zero-filled so that no two blocks overlap."""
    base, img = Elf(elf_path).flat_image()
    chunks = [img[i:i + UF2_PAYLOAD] for i in range(0, len(img), UF2_PAYLOAD)]
    blocks = []
    for n, chunk in enumerate(chunks):
        data = chunk.ljust(476, b"\0")
        blocks.append(struct.pack("<8I", UF2_MAGIC_START0, UF2_MAGIC_START1, UF2_FLAG_FAMILY_ID_PRESENT,
                                  base + n * UF2_PAYLOAD, UF2_PAYLOAD, n, len(chunks), family_id)
                      + data + struct.pack("<I", UF2_MAGIC_END))
    return blocks


def write_uf2(elf_path, uf2_path, family_id):
    blocks = uf2_blocks(elf_path, family_id)
    Path(uf2_path).write_bytes(b"".join(blocks))
    return len(blocks)


def read_uf2(uf2_path):
    """Parses a UF2 file back: list of dicts (for the static checks)."""
    d = Path(uf2_path).read_bytes()
    out = []
    for i in range(0, len(d), 512):
        m0, m1, flags, addr, size, no, num, fam = struct.unpack_from("<8I", d, i)
        (end,) = struct.unpack_from("<I", d, i + 508)
        out.append({"magic_ok": m0 == UF2_MAGIC_START0 and m1 == UF2_MAGIC_START1 and end == UF2_MAGIC_END,
                    "flags": flags, "addr": addr, "size": size, "block_no": no, "num_blocks": num, "family": fam,
                    "data": d[i + 32:i + 32 + size]})
    return out


def find_image_defs(elf_path):
    """Every valid block in the loaded image: list of dicts with address, items and loop link.
    A block is valid if it starts with the start marker, its items chain to a LAST item whose
    size matches, and the end marker follows the link word (datasheet 5.9.1)."""
    base, img = Elf(elf_path).flat_image()
    blocks = []
    for off in range(0, len(img) - 20, 4):
        if struct.unpack_from("<I", img, off)[0] != BLOCK_MARKER_START:
            continue
        pos, items, ok = off + 4, [], False
        while pos + 4 <= len(img):
            head = img[pos]   # bit 7 = size_flag: 0 -> 1-byte size, 1 -> 2-byte size (5.9.1)
            if head == 0xFF:    # 2BS_LAST: type, size (hword, words), pad
                size_words = struct.unpack_from("<H", img, pos + 1)[0]
                items_words = (pos - (off + 4)) // 4
                link, end = struct.unpack_from("<iI", img, pos + 4)
                ok = size_words == items_words and end == BLOCK_MARKER_END
                items.append({"type": "LAST", "size_words": size_words})
                break
            size_words = img[pos + 1] if head & 0x80 == 0 else struct.unpack_from("<H", img, pos + 1)[0]
            if size_words == 0:
                break
            words = struct.unpack_from(f"<{size_words}I", img, pos)
            item = {"type": ITEM_NAMES.get(head, hex(head)), "words": list(words)}
            if head == 0x42:
                item["value"] = words[0] >> 16
            elif head == 0x03:
                item["vector_table"] = words[1]
            elif head == 0x44:
                item["pc"], item["sp"] = words[1], words[2]
            items.append(item)
            pos += 4 * size_words
        if ok:
            blocks.append({"addr": base + off, "items": items, "link": link})
    return blocks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--elf", required=True)
    ap.add_argument("--uf2")
    ap.add_argument("--family", type=lambda x: int(x, 0))
    args = ap.parse_args()
    if args.uf2:
        if args.family is None:
            ap.error("--family is required with --uf2 (0xe48bff59 Arm Secure, 0xe48bff5a RISC-V)")
        print(f"{write_uf2(args.elf, args.uf2, args.family)} blocks -> {args.uf2}")
    for b in find_image_defs(args.elf):
        print(f"block at 0x{b['addr']:08x}, link {b['link']}:")
        for it in b["items"]:
            print("   ", {k: (hex(v) if isinstance(v, int) else v) for k, v in it.items() if k != "words"})


if __name__ == "__main__":
    main()
