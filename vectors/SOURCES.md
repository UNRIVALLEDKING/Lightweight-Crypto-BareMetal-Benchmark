# Known Answer Test (KAT) Sources

Vectors validate every C, C++, Rust and Zig implementation bit for bit, on the host
(`host/`) and inside every QEMU image (`harness/common/kat.c`, generated from these files).

## 1. SIMON 64/128
- Source: Beaulieu et al., "The SIMON and SPECK Families of Lightweight Block Ciphers",
  IACR ePrint 2013/404. Parameters: 64-bit block (n = 32), 128-bit key (m = 4), 44 rounds, sequence z3.
- Vector (key `0001020308090a0b1011121318191a1b`, plaintext `756e64206c696b65`,
  ciphertext `7aa0dfb920fcc844`; the same vector appears in the reference test suite of
  https://github.com/inmcm/Simon_Speck_Ciphers). Byte order: little-endian 32-bit words, y then x.

## 2. PRESENT-80
- Source: Bogdanov et al., "PRESENT: An Ultra-Lightweight Block Cipher", CHES 2007, LNCS 4727, pp. 450-466.
- Vectors (80-bit key, 64-bit block, big-endian):
  - key `00..00`, plaintext `00..00` -> `5579c1387b228445`
  - key `ff..ff`, plaintext `00..00` -> `e72c46c0f5945049`
  - key `00..00`, plaintext `ff..ff` -> `a112ffc72f68417b`
  - key `ff..ff`, plaintext `ff..ff` -> `3333dcd3213210d2`
  (check the last three against the paper's appendix before publication; all implementations here agree with them.)

## 3. Ascon-AEAD128 (NIST SP 800-232)
- Standard: NIST SP 800-232, "Ascon-Based Lightweight Cryptography Standards for Constrained
  Devices" (August 2025), Ascon-AEAD128. Parameters: 128-bit key, nonce and tag; 128-bit rate;
  p[12] for initialisation/finalisation, p[8] for data; little-endian byte order; IV `0x00001000808c0001`.
- Official vectors: all 1,089 in `vectors/official/asconaead128_LWC_AEAD_KAT_128_128.txt`, from the
  designers' reference repository https://github.com/ascon/ascon-c at commit
  `446347f21b209f3921c65ece70027c366cbe1693` (2026-01-28), path `crypto_aead/asconaead128/`, CC0
  (licence in `LICENSE-ascon-c-CC0.txt`). SHA-256 of the file:
  `bbbc34692fe05e5fda0a3b025585622ab3e3747495e5e3655b29aae8c2a4bd33`.
  Note: the `v1.3.0` tag of ascon-c does NOT contain this scheme (it has the earlier `ascon128v13`).
- Independent check: the designers' Python reference (https://github.com/meichlseder/pyascon,
  `ascon.py`, variant `"Ascon-AEAD128"`) reproduces all 1,089 vectors (checked 2026-10-09).
- `ascon_aead128.json` holds a 15-vector subset (Counts 1, 2, 9, 17, 34, 35, 42, 67, 75, 133, 141,
  265, 273, 529, 537) generated from the official file. Key `000102..0f`, nonce `101112..1f`.
- Ascon-128 v1.2 (the CAESAR / LWC-round scheme used before) was removed: it is a different scheme
  with different outputs, and nothing in this study compares against it.
