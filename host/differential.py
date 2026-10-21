#!/usr/bin/env python3
"""
Cross-language differential testing on the host.

1. Random fuzz: N random inputs (fresh OS randomness, seed printed) through every backend;
   every output must be bit-identical across C, C++, Rust and Zig, and decrypt must invert.
2. Deterministic digest: the same xorshift32 stream the firmware uses inside QEMU
   (harness/common/fuzz.c). All backends must agree; the agreed digest is written to
   build/host/fuzz_digest.json, and scripts/parse_log.py compares every QEMU run against it.

Needs all four backends unless --allow-partial (and always at least two).
"""

import json
import random
import secrets
import sys

from lwc_host import FUZZ_ITERATIONS, HOST_LIB_DIR, LWC_SUCCESS, fuzz_digest, load_backends


def agree(label, results, context):
    first_lang, first = next(iter(results.items()))
    for lang, out in results.items():
        if out != first:
            raise AssertionError(f"{label} mismatch: {first_lang}={first.hex()} {lang}={out.hex()} | {context}")


def random_fuzz(backends, iterations, rng):
    for i in range(iterations):
        key, pt = rng.randbytes(16), rng.randbytes(8)
        agree("SIMON", {l: b.simon_encrypt(key, pt) for l, b in backends.items()}, f"key={key.hex()} pt={pt.hex()}")
        key, pt = rng.randbytes(10), rng.randbytes(8)
        agree("PRESENT", {l: b.present_encrypt(key, pt) for l, b in backends.items()}, f"key={key.hex()} pt={pt.hex()}")
        key, nonce = rng.randbytes(16), rng.randbytes(16)
        ad, pt = rng.randbytes(rng.randint(0, 48)), rng.randbytes(rng.randint(0, 80))
        outs = {l: b.ascon_encrypt(key, nonce, ad, pt) for l, b in backends.items()}
        agree("ASCON", outs, f"key={key.hex()} nonce={nonce.hex()} ad={ad.hex()} pt={pt.hex()}")
        for lang, b in backends.items():
            rc, back = b.ascon_decrypt(key, nonce, ad, outs[lang])
            if rc != LWC_SUCCESS or back != pt:
                raise AssertionError(f"ASCON {lang} decrypt does not invert encrypt (iteration {i})")
        if (i + 1) % 2500 == 0:
            print(f"  {i + 1}/{iterations}")


def main():
    backends = load_backends()
    if len(backends) < 2:
        print("[FATAL] differential testing needs at least two backends")
        sys.exit(1)

    seed = secrets.randbits(64)
    iterations = 10000
    print(f"Random differential fuzz over {list(backends)}: {iterations} iterations, seed={seed:#x}")
    try:
        random_fuzz(backends, iterations, random.Random(seed))
    except AssertionError as e:
        print(f"[FATAL] {e}\n        reproduce with seed={seed:#x}")
        sys.exit(1)
    print("  -> outputs bit-identical across all backends")

    print(f"\nDeterministic fuzz digest ({FUZZ_ITERATIONS} iterations, firmware-identical stream):")
    digests = {lang: fuzz_digest(b) for lang, b in backends.items()}
    for lang, d in digests.items():
        print(f"  {lang:5} {d}")
    ref = next(iter(digests.values()))
    if any(d != ref for d in digests.values()) or ref["errors"]:
        print("[FATAL] backends disagree on the deterministic digest, or round-trip errors")
        sys.exit(1)
    out = HOST_LIB_DIR / "fuzz_digest.json"
    out.write_text(json.dumps({"iterations": FUZZ_ITERATIONS, "backends": list(backends), **ref}, indent=2) + "\n")
    print(f"  -> reference digest written to {out}")
    print("\n[ALL DIFFERENTIAL TESTS PASSED]")


if __name__ == "__main__":
    main()
