/**
 * @file backend.h
 * @brief The one cipher backend linked into this image, as a table of function pointers
 *
 * Each image contains exactly one backend (C, C++, Rust or Zig). The build passes
 * -DLWC_BACKEND_PREFIX=lwc_rs (etc.) and -DLWC_BACKEND_LANG="Rust"; backend.c binds the
 * table to that prefix, so the symbol gate can check the image contains that backend
 * and nothing else.
 */

#ifndef LWC_BACKEND_H
#define LWC_BACKEND_H

#include "lwc_api.h"

typedef int32_t (*lwc_simon_init_fn)(lwc_simon64_128_key_t *ctx, const uint8_t *key);
typedef int32_t (*lwc_simon_block_fn)(const lwc_simon64_128_key_t *ctx, const uint8_t *in, uint8_t *out);
typedef int32_t (*lwc_present_init_fn)(lwc_present80_key_t *ctx, const uint8_t *key);
typedef int32_t (*lwc_present_block_fn)(const lwc_present80_key_t *ctx, const uint8_t *in, uint8_t *out);
typedef int32_t (*lwc_ascon_enc_fn)(uint8_t *ct, uint8_t *tag, const uint8_t *pt, size_t pt_len,
                                    const uint8_t *ad, size_t ad_len, const uint8_t *nonce, const uint8_t *key);
typedef int32_t (*lwc_ascon_dec_fn)(uint8_t *pt, const uint8_t *ct, size_t ct_len, const uint8_t *tag,
                                    const uint8_t *ad, size_t ad_len, const uint8_t *nonce, const uint8_t *key);

typedef struct {
    const char *lang;
    lwc_simon_init_fn    simon_init;
    lwc_simon_block_fn   simon_encrypt;
    lwc_simon_block_fn   simon_decrypt;
    lwc_present_init_fn  present_init;
    lwc_present_block_fn present_encrypt;
    lwc_present_block_fn present_decrypt;
    lwc_ascon_enc_fn     ascon_encrypt;
    lwc_ascon_dec_fn     ascon_decrypt;
} lwc_backend_t;

extern const lwc_backend_t lwc_backend;

#endif /* LWC_BACKEND_H */
