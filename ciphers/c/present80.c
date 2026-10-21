/**
 * @file present80.c
 * @brief PRESENT-80 Lightweight Block Cipher C99 Implementation
 */

#include "lwc_api.h"

/* 4-bit PRESENT S-Box and Inverse S-Box */
static const uint8_t SBOX[16] = {
    0xC, 0x5, 0x6, 0xB, 0x9, 0x0, 0xA, 0xD,
    0x3, 0xE, 0xF, 0x8, 0x4, 0x7, 0x1, 0x2
};

static const uint8_t SBOX_INV[16] = {
    0x5, 0xE, 0xF, 0x8, 0xC, 0x1, 0x2, 0xD,
    0xB, 0x4, 0x6, 0x3, 0x0, 0x7, 0x9, 0xA
};

static inline uint64_t load64_be(const uint8_t *b) {
    return (((uint64_t)b[0]) << 56) |
           (((uint64_t)b[1]) << 48) |
           (((uint64_t)b[2]) << 40) |
           (((uint64_t)b[3]) << 32) |
           (((uint64_t)b[4]) << 24) |
           (((uint64_t)b[5]) << 16) |
           (((uint64_t)b[6]) << 8)  |
           (((uint64_t)b[7]));
}

static inline void store64_be(uint8_t *b, uint64_t v) {
    b[0] = (uint8_t)(v >> 56);
    b[1] = (uint8_t)(v >> 48);
    b[2] = (uint8_t)(v >> 40);
    b[3] = (uint8_t)(v >> 32);
    b[4] = (uint8_t)(v >> 24);
    b[5] = (uint8_t)(v >> 16);
    b[6] = (uint8_t)(v >> 8);
    b[7] = (uint8_t)(v);
}

static inline uint64_t sbox_layer(uint64_t state) {
    uint64_t out = 0;
    for (int i = 0; i < 16; i++) {
        uint8_t nibble = (uint8_t)((state >> (i * 4)) & 0x0F);
        out |= ((uint64_t)SBOX[nibble]) << (i * 4);
    }
    return out;
}

static inline uint64_t sbox_layer_inv(uint64_t state) {
    uint64_t out = 0;
    for (int i = 0; i < 16; i++) {
        uint8_t nibble = (uint8_t)((state >> (i * 4)) & 0x0F);
        out |= ((uint64_t)SBOX_INV[nibble]) << (i * 4);
    }
    return out;
}

static inline uint64_t p_layer(uint64_t state) {
    uint64_t out = 0;
    for (int i = 0; i < 64; i++) {
        uint64_t bit = (state >> i) & 1ULL;
        int dest = (i == 63) ? 63 : (i * 16) % 63;
        out |= (bit << dest);
    }
    return out;
}

static inline uint64_t p_layer_inv(uint64_t state) {
    uint64_t out = 0;
    for (int i = 0; i < 64; i++) {
        uint64_t bit = (state >> i) & 1ULL;
        int dest = (i == 63) ? 63 : (i * 4) % 63;
        out |= (bit << dest);
    }
    return out;
}

int32_t lwc_c_present80_init(lwc_present80_key_t *ctx, const uint8_t *key) {
    if (!ctx || !key) {
        return LWC_ERR_NULL_PTR;
    }

    uint16_t k_hi = ((uint16_t)key[0] << 8) | (uint16_t)key[1];
    uint64_t k_lo = load64_be(key + 2);

    for (int round = 0; round < LWC_PRESENT80_ROUND_KEYS; round++) {
        /* Round key is 64 most significant bits */
        ctx->round_keys[round] = ((uint64_t)k_hi << 48) | (k_lo >> 16);

        if (round < LWC_PRESENT80_ROUNDS) {
            /* 1. Rotate left 61 bits (rotate right 19 bits) */
            uint16_t new_hi = (uint16_t)((k_lo >> 3) & 0xFFFF);
            uint64_t new_lo = ((k_lo & 7ULL) << 61) | ((uint64_t)k_hi << 45) | (k_lo >> 19);

            /* 2. S-box on 4 highest bits */
            uint8_t top_nibble = (uint8_t)(new_hi >> 12);
            new_hi = (uint16_t)((SBOX[top_nibble] << 12) | (new_hi & 0x0FFF));

            /* 3. Round counter addition on bits 19..15 */
            new_lo ^= ((uint64_t)(round + 1) << 15);

            k_hi = new_hi;
            k_lo = new_lo;
        }
    }

    return LWC_SUCCESS;
}

int32_t lwc_c_present80_encrypt_block(const lwc_present80_key_t *ctx, const uint8_t *pt, uint8_t *ct) {
    if (!ctx || !pt || !ct) {
        return LWC_ERR_NULL_PTR;
    }

    uint64_t state = load64_be(pt);

    for (int i = 0; i < LWC_PRESENT80_ROUNDS; i++) {
        state ^= ctx->round_keys[i];
        state = sbox_layer(state);
        state = p_layer(state);
    }

    state ^= ctx->round_keys[LWC_PRESENT80_ROUNDS];
    store64_be(ct, state);

    return LWC_SUCCESS;
}

int32_t lwc_c_present80_decrypt_block(const lwc_present80_key_t *ctx, const uint8_t *ct, uint8_t *pt) {
    if (!ctx || !ct || !pt) {
        return LWC_ERR_NULL_PTR;
    }

    uint64_t state = load64_be(ct);

    for (int i = LWC_PRESENT80_ROUNDS; i > 0; i--) {
        state ^= ctx->round_keys[i];
        state = p_layer_inv(state);
        state = sbox_layer_inv(state);
    }

    state ^= ctx->round_keys[0];
    store64_be(pt, state);

    return LWC_SUCCESS;
}
