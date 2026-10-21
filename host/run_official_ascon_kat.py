#!/usr/bin/env python3
"""
Runs ALL official Ascon-AEAD128 (NIST SP 800-232) known-answer vectors (1,089) against
every host backend (C, C++, Rust, Zig), encrypt and decrypt, plus a tampered-tag check.

Source file: vectors/official/asconaead128_LWC_AEAD_KAT_128_128.txt
(ascon-c commit 446347f2, crypto_aead/asconaead128, CC0; see vectors/SOURCES.md).
Exit code is non-zero on any mismatch or if a backend is missing (unless --allow-partial).
"""

import sys

from lwc_host import LWC_ERR_AUTH_FAIL, LWC_SUCCESS, OFFICIAL_ASCON_KAT, load_backends, parse_lwc_kat


def main():
    backends = load_backends()
    vectors = parse_lwc_kat(OFFICIAL_ASCON_KAT)
    print(f"Loaded {len(vectors)} official Ascon-AEAD128 vectors from {OFFICIAL_ASCON_KAT.name}")
    bad_total = 0
    for lang, b in backends.items():
        bad = 0
        for v in vectors:
            if b.ascon_encrypt(v["key"], v["nonce"], v["ad"], v["pt"]) != v["ct"]:
                bad += 1
                continue
            rc, back = b.ascon_decrypt(v["key"], v["nonce"], v["ad"], v["ct"])
            if rc != LWC_SUCCESS or back != v["pt"]:
                bad += 1
                continue
            tampered = bytearray(v["ct"])
            tampered[-1] ^= 0x80
            rc, back = b.ascon_decrypt(v["key"], v["nonce"], v["ad"], bytes(tampered))
            if rc != LWC_ERR_AUTH_FAIL or any(back):
                bad += 1
        print(f"  {lang:5} {b.path.name:14} {len(vectors) - bad}/{len(vectors)} OK (encrypt, decrypt, tampered tag)")
        bad_total += bad
    if bad_total:
        print("[FATAL] official KAT failed")
        sys.exit(1)
    print(f"[PASS] all official vectors passed for {list(backends)}")


if __name__ == "__main__":
    main()
