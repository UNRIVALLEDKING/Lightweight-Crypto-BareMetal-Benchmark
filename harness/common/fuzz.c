/**
 * @file fuzz.c
 * @brief Deterministic differential fuzz digest
 *
 * Generates the same xorshift32 input stream as host/lwc_host.py:fuzz_digest(), runs
 * every cipher on it and folds all outputs into one FNV-1a 32 hash per cipher. Every
 * image of the matrix (any language, compiler, profile, target) must print the same
 * digests as the host libraries; scripts/parse_log.py enforces that. Any change here
 * must be made in lwc_host.py too.
 */

#include "checks.h"
#include "io.h"

#define FUZZ_SEED       0x2545F491u
#define FUZZ_ITERATIONS 1000
#define FNV_OFFSET      0x811C9DC5u
#define FNV_PRIME       0x01000193u

static uint32_t s_rng;

static uint32_t rng_next(void) {
    uint32_t x = s_rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    s_rng = x;
    return x;
}

static void rng_bytes(uint8_t *out, size_t n) {
    uint32_t w = 0;
    for (size_t i = 0; i < n; i++) {
        if (i % 4 == 0) {
            w = rng_next();
        }
        out[i] = (uint8_t)(w >> (8 * (i % 4)));
    }
}

static uint32_t fnv1a(uint32_t h, const uint8_t *p, size_t n) {
    for (size_t i = 0; i < n; i++) {
        h = (h ^ p[i]) * FNV_PRIME;
    }
    return h;
}

static int differs(const uint8_t *a, const uint8_t *b, size_t n) {
    for (size_t i = 0; i < n; i++) {
        if (a[i] != b[i]) {
            return 1;
        }
    }
    return 0;
}

int lwc_run_fuzz(const lwc_backend_t *b) {
    static uint8_t ad[32], pt[64], ct[64 + 16], back[64];
    uint8_t key[16], nonce[16], blk[8], out[8], dec[8];
    uint32_t h_simon = FNV_OFFSET, h_present = FNV_OFFSET, h_ascon = FNV_OFFSET;
    int errors = 0;

    s_rng = FUZZ_SEED;
    for (uint32_t i = 0; i < FUZZ_ITERATIONS; i++) {
        lwc_simon64_128_key_t sk;
        rng_bytes(key, 16);
        rng_bytes(blk, 8);
        errors += b->simon_init(&sk, key) != LWC_SUCCESS;
        errors += b->simon_encrypt(&sk, blk, out) != LWC_SUCCESS;
        errors += b->simon_decrypt(&sk, out, dec) != LWC_SUCCESS || differs(dec, blk, 8);
        h_simon = fnv1a(h_simon, out, 8);

        lwc_present80_key_t pk;
        rng_bytes(key, 10);
        rng_bytes(blk, 8);
        errors += b->present_init(&pk, key) != LWC_SUCCESS;
        errors += b->present_encrypt(&pk, blk, out) != LWC_SUCCESS;
        errors += b->present_decrypt(&pk, out, dec) != LWC_SUCCESS || differs(dec, blk, 8);
        h_present = fnv1a(h_present, out, 8);

        rng_bytes(key, 16);
        rng_bytes(nonce, 16);
        size_t ad_len = rng_next() % 33;
        size_t pt_len = rng_next() % 65;
        rng_bytes(ad, ad_len);
        rng_bytes(pt, pt_len);
        uint8_t *tag = ct + pt_len;
        errors += b->ascon_encrypt(ct, tag, pt, pt_len, ad, ad_len, nonce, key) != LWC_SUCCESS;
        errors += b->ascon_decrypt(back, ct, pt_len, tag, ad, ad_len, nonce, key) != LWC_SUCCESS
                  || differs(back, pt, pt_len);
        if (i % 8 == 0) {
            uint8_t bad[16];
            for (int j = 0; j < 16; j++) {
                bad[j] = tag[j];
            }
            bad[(i / 8) % 16] ^= 0x01; /* flip one tag bit */
            errors += b->ascon_decrypt(back, ct, pt_len, bad, ad, ad_len, nonce, key) != LWC_ERR_AUTH_FAIL;
        }
        h_ascon = fnv1a(h_ascon, ct, pt_len + 16);
    }

    lwc_printf("FUZZ,%u,%08x,%08x,%08x,%d\n", (unsigned)FUZZ_ITERATIONS,
               (unsigned)h_simon, (unsigned)h_present, (unsigned)h_ascon, errors);
    return errors;
}
