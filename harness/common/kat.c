/**
 * @file kat.c
 * @brief Known-answer tests inside the image: SIMON, PRESENT and all 1,089 official
 *        Ascon-AEAD128 vectors (encrypt, decrypt and a tampered tag)
 */

#include "checks.h"
#include "io.h"
#include "lwc_kat_vectors.h" /* generated into build/<cell>/gen by scripts/gen_kat_header.py */

static int bytes_equal(const uint8_t *a, const uint8_t *b, size_t n) {
    uint8_t d = 0;
    for (size_t i = 0; i < n; i++) {
        d |= a[i] ^ b[i];
    }
    return d == 0;
}

static int kat_simon(const lwc_backend_t *b) {
    int pass = 0;
    for (int i = 0; i < LWC_KAT_SIMON_COUNT; i++) {
        const lwc_kat_block_t *v = &lwc_kat_simon[i];
        lwc_simon64_128_key_t ctx;
        uint8_t ct[8], pt[8];
        int ok = b->simon_init(&ctx, v->key) == LWC_SUCCESS;
        ok &= b->simon_encrypt(&ctx, v->pt, ct) == LWC_SUCCESS && bytes_equal(ct, v->ct, 8);
        ok &= b->simon_decrypt(&ctx, v->ct, pt) == LWC_SUCCESS && bytes_equal(pt, v->pt, 8);
        pass += ok;
    }
    lwc_printf("KAT,SIMON64_128,%d,%d\n", pass, LWC_KAT_SIMON_COUNT);
    return LWC_KAT_SIMON_COUNT - pass;
}

static int kat_present(const lwc_backend_t *b) {
    int pass = 0;
    for (int i = 0; i < LWC_KAT_PRESENT_COUNT; i++) {
        const lwc_kat_block_t *v = &lwc_kat_present[i];
        lwc_present80_key_t ctx;
        uint8_t ct[8], pt[8];
        int ok = b->present_init(&ctx, v->key) == LWC_SUCCESS;
        ok &= b->present_encrypt(&ctx, v->pt, ct) == LWC_SUCCESS && bytes_equal(ct, v->ct, 8);
        ok &= b->present_decrypt(&ctx, v->ct, pt) == LWC_SUCCESS && bytes_equal(pt, v->pt, 8);
        pass += ok;
    }
    lwc_printf("KAT,PRESENT80,%d,%d\n", pass, LWC_KAT_PRESENT_COUNT);
    return LWC_KAT_PRESENT_COUNT - pass;
}

static int kat_ascon(const lwc_backend_t *b) {
    static uint8_t ct[LWC_KAT_ASCON_MAX_PT], pt[LWC_KAT_ASCON_MAX_PT];
    int pass = 0;
    for (int i = 0; i < LWC_KAT_ASCON_COUNT; i++) {
        const lwc_kat_ascon_t *v = &lwc_kat_ascon[i];
        const uint8_t *key = &lwc_kat_ascon_blob[v->off];
        const uint8_t *nonce = key + 16;
        const uint8_t *ad = nonce + 16;
        const uint8_t *msg = ad + v->ad_len;
        const uint8_t *exp_ct = msg + v->pt_len;
        const uint8_t *exp_tag = exp_ct + v->pt_len;
        uint8_t tag[16], bad_tag[16];

        int ok = b->ascon_encrypt(ct, tag, msg, v->pt_len, ad, v->ad_len, nonce, key) == LWC_SUCCESS;
        ok &= bytes_equal(ct, exp_ct, v->pt_len) && bytes_equal(tag, exp_tag, 16);

        ok &= b->ascon_decrypt(pt, exp_ct, v->pt_len, exp_tag, ad, v->ad_len, nonce, key) == LWC_SUCCESS;
        ok &= bytes_equal(pt, msg, v->pt_len);

        for (int j = 0; j < 16; j++) {
            bad_tag[j] = exp_tag[j];
        }
        bad_tag[15] ^= 0x80;
        ok &= b->ascon_decrypt(pt, exp_ct, v->pt_len, bad_tag, ad, v->ad_len, nonce, key) == LWC_ERR_AUTH_FAIL;
        for (int j = 0; j < v->pt_len; j++) {
            ok &= pt[j] == 0; /* plaintext must be wiped on failure */
        }
        pass += ok;
    }
    lwc_printf("KAT,ASCON_AEAD128,%d,%d\n", pass, LWC_KAT_ASCON_COUNT);
    return LWC_KAT_ASCON_COUNT - pass;
}

int lwc_run_kats(const lwc_backend_t *b) {
    return kat_simon(b) + kat_present(b) + kat_ascon(b);
}
