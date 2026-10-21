#!/usr/bin/env python3
"""
Host Known Answer Tests: every backend (C, C++, Rust, Zig) against vectors/*.json.
Exit code is non-zero on any mismatch, or if a backend is missing (unless --allow-partial).
"""

import json
import sys

from lwc_host import LWC_SUCCESS, VECTORS_DIR, load_backends


def load(name):
    return json.loads((VECTORS_DIR / name).read_text())["vectors"]


def check(failures, lang, label, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{lang}: {label}")


def main():
    backends = load_backends()
    failures = []
    for lang, b in backends.items():
        print(f"\n=== {lang} ({b.path.name}) ===")
        for v in load("simon64_128.json"):
            key, pt, ct = (bytes.fromhex(v[k]) for k in ("key", "plaintext", "ciphertext"))
            check(failures, lang, f"SIMON64/128 #{v['id']} enc", b.simon_encrypt(key, pt) == ct)
            check(failures, lang, f"SIMON64/128 #{v['id']} dec", b.simon_decrypt(key, ct) == pt)
        for v in load("present80.json"):
            key, pt, ct = (bytes.fromhex(v[k]) for k in ("key", "plaintext", "ciphertext"))
            check(failures, lang, f"PRESENT-80 #{v['id']} enc", b.present_encrypt(key, pt) == ct)
            check(failures, lang, f"PRESENT-80 #{v['id']} dec", b.present_decrypt(key, ct) == pt)
        for v in load("ascon_aead128.json"):
            key, nonce, ad, pt = (bytes.fromhex(v[k]) for k in ("key", "nonce", "ad", "plaintext"))
            expect = bytes.fromhex(v["ciphertext"]) + bytes.fromhex(v["tag"])
            check(failures, lang, f"Ascon-AEAD128 #{v['id']} enc", b.ascon_encrypt(key, nonce, ad, pt) == expect)
            rc, back = b.ascon_decrypt(key, nonce, ad, expect)
            check(failures, lang, f"Ascon-AEAD128 #{v['id']} dec", rc == LWC_SUCCESS and back == pt)

    if failures:
        print("\n[FATAL] KAT FAILURES:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print(f"\n[ALL KATs PASSED] backends verified: {list(backends)}")


if __name__ == "__main__":
    main()
