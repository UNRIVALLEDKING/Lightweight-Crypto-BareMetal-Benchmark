/**
 * @file simon64_128.c
 * @brief NSA SIMON 64/128 Block Cipher C99 Implementation
 */

#include "lwc_api.h"

#define ROTL32(x, r) (((x) << (r)) | ((x) >> (32 - (r))))
#define ROTR32(x, r) (((x) >> (r)) | ((x) << (32 - (r))))

/* 62-bit z3 constant sequence for SIMON 64/128 */
static const uint8_t Z3[62] = {
    1,1,0,1,1,0,1,1,1,0,1,0,1,1,0,0,0,1,1,0,0,1,0,1,1,1,1,0,0,0,
    0,0,0,1,0,0,1,0,0,0,1,0,1,0,0,1,1,1,0,0,1,1,0,1,0,0,0,0,1,1,1,1
};

static inline uint32_t load32_le(const uint8_t *b) {
    return ((uint32_t)b[0]) |
           (((uint32_t)b[1]) << 8) |
           (((uint32_t)b[2]) << 16) |
           (((uint32_t)b[3]) << 24);
}

static inline void store32_le(uint8_t *b, uint32_t v) {
    b[0] = (uint8_t)(v);
    b[1] = (uint8_t)(v >> 8);
    b[2] = (uint8_t)(v >> 16);
    b[3] = (uint8_t)(v >> 24);
}

static inline uint32_t simon_f(uint32_t x) {
    return (ROTL32(x, 1) & ROTL32(x, 8)) ^ ROTL32(x, 2);
}

int32_t lwc_c_simon64_128_init(lwc_simon64_128_key_t *ctx, const uint8_t *key) {
    if (!ctx || !key) {
        return LWC_ERR_NULL_PTR;
    }

    ctx->round_keys[0] = load32_le(key + 0);
    ctx->round_keys[1] = load32_le(key + 4);
    ctx->round_keys[2] = load32_le(key + 8);
    ctx->round_keys[3] = load32_le(key + 12);

    for (int i = 4; i < LWC_SIMON64_128_ROUNDS; i++) {
        uint32_t tmp = ROTR32(ctx->round_keys[i - 1], 3);
        tmp ^= ctx->round_keys[i - 3];
        tmp ^= ROTR32(tmp, 1);
        ctx->round_keys[i] = ~ctx->round_keys[i - 4] ^ tmp ^ Z3[(i - 4) % 62] ^ 3;
    }

    return LWC_SUCCESS;
}

int32_t lwc_c_simon64_128_encrypt_block(const lwc_simon64_128_key_t *ctx, const uint8_t *pt, uint8_t *ct) {
    if (!ctx || !pt || !ct) {
        return LWC_ERR_NULL_PTR;
    }

    uint32_t x = load32_le(pt + 4);
    uint32_t y = load32_le(pt + 0);

    for (int i = 0; i < LWC_SIMON64_128_ROUNDS; i++) {
        uint32_t tmp = simon_f(x) ^ y ^ ctx->round_keys[i];
        y = x;
        x = tmp;
    }

    store32_le(ct + 4, x);
    store32_le(ct + 0, y);

    return LWC_SUCCESS;
}

int32_t lwc_c_simon64_128_decrypt_block(const lwc_simon64_128_key_t *ctx, const uint8_t *ct, uint8_t *pt) {
    if (!ctx || !ct || !pt) {
        return LWC_ERR_NULL_PTR;
    }

    uint32_t x = load32_le(ct + 4);
    uint32_t y = load32_le(ct + 0);

    for (int i = LWC_SIMON64_128_ROUNDS - 1; i >= 0; i--) {
        uint32_t tmp = simon_f(y) ^ x ^ ctx->round_keys[i];
        x = y;
        y = tmp;
    }

    store32_le(pt + 4, x);
    store32_le(pt + 0, y);

    return LWC_SUCCESS;
}
