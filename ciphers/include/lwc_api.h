/**
 * @file lwc_api.h
 * @brief C ABI shared by every cipher backend (C, C++, Rust, Zig)
 *
 * Every backend exports the same functions under its own prefix (see
 * LWC_DECLARE_BACKEND at the end), so any number of backends can be linked
 * into one image without a symbol clash.
 */

#ifndef LWC_API_H
#define LWC_API_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Return Status Codes */
#define LWC_SUCCESS            ( 0)
#define LWC_ERR_NULL_PTR       (-1)
#define LWC_ERR_AUTH_FAIL      (-2)
#define LWC_ERR_INVALID_PARAM  (-3)

/* ========================================================================= */
/* SIMON 64/128 (64-bit block, 128-bit key, 44 rounds)                       */
/* ========================================================================= */

#define LWC_SIMON64_128_BLOCK_BYTES 8
#define LWC_SIMON64_128_KEY_BYTES   16
#define LWC_SIMON64_128_ROUNDS      44

typedef struct {
    uint32_t round_keys[LWC_SIMON64_128_ROUNDS];
} lwc_simon64_128_key_t;

/*
 * <P>_simon64_128_init(ctx, key)          16-byte key (little-endian words) -> round keys
 * <P>_simon64_128_encrypt_block(ctx, pt, ct)   8-byte block
 * <P>_simon64_128_decrypt_block(ctx, ct, pt)   8-byte block
 * All return LWC_SUCCESS or LWC_ERR_NULL_PTR.
 */

/* ========================================================================= */
/* PRESENT-80 (64-bit block, 80-bit key, 31 rounds)                          */
/* ========================================================================= */

#define LWC_PRESENT80_BLOCK_BYTES 8
#define LWC_PRESENT80_KEY_BYTES   10
#define LWC_PRESENT80_ROUNDS      31
#define LWC_PRESENT80_ROUND_KEYS  32

typedef struct {
    uint64_t round_keys[LWC_PRESENT80_ROUND_KEYS];
} lwc_present80_key_t;

/*
 * <P>_present80_init(ctx, key)            10-byte (80-bit) key -> 32 round keys
 * <P>_present80_encrypt_block(ctx, pt, ct)     8-byte block, big-endian
 * <P>_present80_decrypt_block(ctx, ct, pt)     8-byte block, big-endian
 * All return LWC_SUCCESS or LWC_ERR_NULL_PTR.
 */

/* ========================================================================= */
/* Ascon-AEAD128 (NIST SP 800-232): 128-bit key/nonce/tag, 128-bit rate      */
/* ========================================================================= */

#define LWC_ASCON_AEAD128_KEY_BYTES   16
#define LWC_ASCON_AEAD128_NONCE_BYTES 16
#define LWC_ASCON_AEAD128_TAG_BYTES   16
#define LWC_ASCON_AEAD128_RATE_BYTES  16

/*
 * <P>_ascon_aead128_encrypt(ct, tag, pt, pt_len, ad, ad_len, nonce, key)
 *     ct receives pt_len bytes, tag receives 16 bytes.
 * <P>_ascon_aead128_decrypt(pt, ct, ct_len, tag, ad, ad_len, nonce, key)
 *     Returns LWC_SUCCESS, or LWC_ERR_AUTH_FAIL (pt is then zeroed).
 * pt/ct/ad may be NULL when their length is 0.
 */

/* ========================================================================= */
/* One set of entry points per backend:                                     */
/*   C: lwc_c_*   C++: lwc_cpp_*   Rust: lwc_rs_*   Zig: lwc_zig_*           */
/* ========================================================================= */
#define LWC_DECLARE_BACKEND(P)                                                              \
    int32_t P##_simon64_128_init(lwc_simon64_128_key_t *ctx, const uint8_t *key);           \
    int32_t P##_simon64_128_encrypt_block(const lwc_simon64_128_key_t *ctx, const uint8_t *pt, uint8_t *ct); \
    int32_t P##_simon64_128_decrypt_block(const lwc_simon64_128_key_t *ctx, const uint8_t *ct, uint8_t *pt); \
    int32_t P##_present80_init(lwc_present80_key_t *ctx, const uint8_t *key);               \
    int32_t P##_present80_encrypt_block(const lwc_present80_key_t *ctx, const uint8_t *pt, uint8_t *ct);     \
    int32_t P##_present80_decrypt_block(const lwc_present80_key_t *ctx, const uint8_t *ct, uint8_t *pt);     \
    int32_t P##_ascon_aead128_encrypt(uint8_t *ct, uint8_t *tag, const uint8_t *pt, size_t pt_len, \
                                      const uint8_t *ad, size_t ad_len, const uint8_t *nonce, const uint8_t *key); \
    int32_t P##_ascon_aead128_decrypt(uint8_t *pt, const uint8_t *ct, size_t ct_len, const uint8_t *tag, \
                                      const uint8_t *ad, size_t ad_len, const uint8_t *nonce, const uint8_t *key);

LWC_DECLARE_BACKEND(lwc_c)
LWC_DECLARE_BACKEND(lwc_cpp)
LWC_DECLARE_BACKEND(lwc_rs)
LWC_DECLARE_BACKEND(lwc_rso)
LWC_DECLARE_BACKEND(lwc_zig)

#ifdef __cplusplus
}
#endif

#endif /* LWC_API_H */
