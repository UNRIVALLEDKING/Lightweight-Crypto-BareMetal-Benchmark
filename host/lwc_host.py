"""
Shared host-side bindings for the four cipher backends (C, C++, Rust, Zig).

Libraries are loaded from build/host/ (written by `scripts/build_all.py --target host`).
This module also holds the reference definition of the deterministic fuzz digest that the
firmware computes inside QEMU (harness/common/fuzz.c). The two MUST stay identical.
"""

import ctypes
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_LIB_DIR = REPO_ROOT / "build" / "host"
VECTORS_DIR = REPO_ROOT / "vectors"
OFFICIAL_ASCON_KAT = VECTORS_DIR / "official" / "asconaead128_LWC_AEAD_KAT_128_128.txt"

LANGS = ["C", "C++", "Rust", "Rust (opt)", "Zig"]
PREFIX = {"C": "lwc_c_", "C++": "lwc_cpp_", "Rust": "lwc_rs_", "Rust (opt)": "lwc_rso_", "Zig": "lwc_zig_"}
LIB_STEM = {"C": "lwc_c", "C++": "lwc_cpp", "Rust": "lwc_rust", "Rust (opt)": "lwc_rust_opt", "Zig": "lwc_zig"}

LWC_SUCCESS = 0
LWC_ERR_AUTH_FAIL = -2

u8 = ctypes.c_uint8
P = ctypes.POINTER


class SimonKey(ctypes.Structure):
    _fields_ = [("round_keys", ctypes.c_uint32 * 44)]


class PresentKey(ctypes.Structure):
    _fields_ = [("round_keys", ctypes.c_uint64 * 32)]


def _buf(data, size=None):
    n = len(data) if size is None else size
    return (u8 * max(n, 1))(*data)


class Backend:
    """One loaded backend library with byte-level helpers."""

    def __init__(self, lang, path):
        self.lang, self.path = lang, path
        lib = ctypes.CDLL(str(path))
        pre = PREFIX[lang]

        def fn(name, argtypes):
            f = getattr(lib, pre + name)
            f.argtypes, f.restype = argtypes, ctypes.c_int32
            return f

        self._simon_init = fn("simon64_128_init", [P(SimonKey), P(u8)])
        self._simon_enc = fn("simon64_128_encrypt_block", [P(SimonKey), P(u8), P(u8)])
        self._simon_dec = fn("simon64_128_decrypt_block", [P(SimonKey), P(u8), P(u8)])
        self._present_init = fn("present80_init", [P(PresentKey), P(u8)])
        self._present_enc = fn("present80_encrypt_block", [P(PresentKey), P(u8), P(u8)])
        self._present_dec = fn("present80_decrypt_block", [P(PresentKey), P(u8), P(u8)])
        self._ascon_enc = fn("ascon_aead128_encrypt",   # ct, tag, pt, pt_len, ad, ad_len, nonce, key
                             [P(u8), P(u8), P(u8), ctypes.c_size_t, P(u8), ctypes.c_size_t, P(u8), P(u8)])
        self._ascon_dec = fn("ascon_aead128_decrypt",   # pt, ct, ct_len, tag, ad, ad_len, nonce, key
                             [P(u8), P(u8), ctypes.c_size_t, P(u8), P(u8), ctypes.c_size_t, P(u8), P(u8)])

    def _block(self, key_t, init, op, key, block):
        ctx, out = key_t(), (u8 * 8)()
        assert init(ctypes.byref(ctx), _buf(key)) == LWC_SUCCESS
        assert op(ctypes.byref(ctx), _buf(block), out) == LWC_SUCCESS
        return bytes(out)

    def simon_encrypt(self, key, pt):
        return self._block(SimonKey, self._simon_init, self._simon_enc, key, pt)

    def simon_decrypt(self, key, ct):
        return self._block(SimonKey, self._simon_init, self._simon_dec, key, ct)

    def present_encrypt(self, key, pt):
        return self._block(PresentKey, self._present_init, self._present_enc, key, pt)

    def present_decrypt(self, key, ct):
        return self._block(PresentKey, self._present_init, self._present_dec, key, ct)

    def ascon_encrypt(self, key, nonce, ad, pt):
        """Returns ct || tag."""
        ct, tag = (u8 * max(len(pt), 1))(), (u8 * 16)()
        rc = self._ascon_enc(ct, tag, _buf(pt) if pt else None, len(pt),
                             _buf(ad) if ad else None, len(ad), _buf(nonce), _buf(key))
        assert rc == LWC_SUCCESS, f"{self.lang} ascon encrypt returned {rc}"
        return bytes(ct)[:len(pt)] + bytes(tag)

    def ascon_decrypt(self, key, nonce, ad, ct_and_tag):
        """Returns (status, plaintext)."""
        ct, tag = ct_and_tag[:-16], ct_and_tag[-16:]
        pt = (u8 * max(len(ct), 1))()
        rc = self._ascon_dec(pt, _buf(ct) if ct else None, len(ct), _buf(tag),
                             _buf(ad) if ad else None, len(ad), _buf(nonce), _buf(key))
        return rc, bytes(pt)[:len(ct)]


def library_path(lang):
    stem = LIB_STEM[lang]
    for name in (f"{stem}.dll", f"lib{stem}.so", f"lib{stem}.dylib"):
        p = HOST_LIB_DIR / name
        if p.exists():
            return p
    return None


def load_backends(argv=None):
    """Load every built backend. Exits non-zero if one is missing, unless --allow-partial."""
    argv = sys.argv if argv is None else argv
    allow_partial = "--allow-partial" in argv
    loaded, missing = {}, []
    for lang in LANGS:
        path = library_path(lang)
        if path is None:
            missing.append(lang)
            continue
        loaded[lang] = Backend(lang, path)
    if missing:
        print(f"[{'WARN' if allow_partial else 'FATAL'}] host library missing for {missing} in {HOST_LIB_DIR}")
        print("        build them with: python scripts/build_all.py --target host")
        if not allow_partial or not loaded:
            sys.exit(1)
    return loaded


def parse_lwc_kat(path):
    """Parse an LWC-format AEAD KAT file (CT field = ciphertext || tag)."""
    vectors = []
    for block in Path(path).read_text().strip().split("\n\n"):
        f = {k.strip(): v.strip() for k, _, v in (line.partition("=") for line in block.splitlines())}
        vectors.append({"count": int(f["Count"]), "key": bytes.fromhex(f["Key"]),
                        "nonce": bytes.fromhex(f["Nonce"]), "pt": bytes.fromhex(f["PT"]),
                        "ad": bytes.fromhex(f["AD"]), "ct": bytes.fromhex(f["CT"])})
    return vectors


# ---------------------------------------------------------------------------
# Deterministic fuzz digest (mirror of harness/common/fuzz.c)
# ---------------------------------------------------------------------------
FUZZ_SEED = 0x2545F491
FUZZ_ITERATIONS = 1000
FNV_OFFSET, FNV_PRIME = 0x811C9DC5, 0x01000193


class XorShift32:
    def __init__(self, seed=FUZZ_SEED):
        self.x = seed

    def next(self):
        x = self.x
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.x = x
        return x

    def bytes(self, n):
        out, w = bytearray(), 0
        for i in range(n):
            if i % 4 == 0:
                w = self.next()
            out.append((w >> (8 * (i % 4))) & 0xFF)
        return bytes(out)


def fnv1a(h, data):
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & 0xFFFFFFFF
    return h


def fuzz_digest(backend, iterations=FUZZ_ITERATIONS):
    """Returns {"SIMON64_128": hex, "PRESENT80": hex, "ASCON_AEAD128": hex, "errors": n}."""
    rng, errors = XorShift32(), 0
    h_simon = h_present = h_ascon = FNV_OFFSET
    for i in range(iterations):
        key, pt = rng.bytes(16), rng.bytes(8)
        ct = backend.simon_encrypt(key, pt)
        errors += backend.simon_decrypt(key, ct) != pt
        h_simon = fnv1a(h_simon, ct)

        key, pt = rng.bytes(10), rng.bytes(8)
        ct = backend.present_encrypt(key, pt)
        errors += backend.present_decrypt(key, ct) != pt
        h_present = fnv1a(h_present, ct)

        key, nonce = rng.bytes(16), rng.bytes(16)
        ad_len, pt_len = rng.next() % 33, rng.next() % 65
        ad, pt = rng.bytes(ad_len), rng.bytes(pt_len)
        ct = backend.ascon_encrypt(key, nonce, ad, pt)
        rc, back = backend.ascon_decrypt(key, nonce, ad, ct)
        errors += rc != LWC_SUCCESS or back != pt
        if i % 8 == 0:
            bad = bytearray(ct)
            bad[-16 + (i // 8) % 16] ^= 0x01            # flip one tag bit
            rc, _ = backend.ascon_decrypt(key, nonce, ad, bytes(bad))
            errors += rc != LWC_ERR_AUTH_FAIL
        h_ascon = fnv1a(h_ascon, ct)
    return {"SIMON64_128": f"{h_simon:08x}", "PRESENT80": f"{h_present:08x}",
            "ASCON_AEAD128": f"{h_ascon:08x}", "errors": errors}
