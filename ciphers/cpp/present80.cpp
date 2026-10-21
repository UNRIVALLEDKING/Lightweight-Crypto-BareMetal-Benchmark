/**
 * @file present80.cpp
 * @brief PRESENT-80 block cipher, freestanding C++17 (mirrors ciphers/c/present80.c)
 */

#include "lwc_cpp_util.hpp"

namespace {

using lwc::detail::load64_be;
using lwc::detail::store64_be;

constexpr int kRounds = LWC_PRESENT80_ROUNDS;
constexpr int kRoundKeys = LWC_PRESENT80_ROUND_KEYS;

/* 4-bit PRESENT S-Box and Inverse S-Box */
constexpr uint8_t SBOX[16] = {
    0xC, 0x5, 0x6, 0xB, 0x9, 0x0, 0xA, 0xD,
    0x3, 0xE, 0xF, 0x8, 0x4, 0x7, 0x1, 0x2
};

constexpr uint8_t SBOX_INV[16] = {
    0x5, 0xE, 0xF, 0x8, 0xC, 0x1, 0x2, 0xD,
    0xB, 0x4, 0x6, 0x3, 0x0, 0x7, 0x9, 0xA
};

/* The inverse table really inverts the forward one (checked at compile time). */
constexpr bool sbox_inverse_ok() {
    for (int i = 0; i < 16; i++) {
        if (SBOX_INV[SBOX[i]] != i) {
            return false;
        }
    }
    return true;
}
static_assert(sbox_inverse_ok(), "SBOX_INV is not the inverse of SBOX");

inline uint64_t sbox_layer(uint64_t state, const uint8_t (&box)[16]) {
    uint64_t out = 0;
    for (int i = 0; i < 16; i++) {
        const uint8_t nibble = static_cast<uint8_t>((state >> (i * 4)) & 0x0F);
        out |= static_cast<uint64_t>(box[nibble]) << (i * 4);
    }
    return out;
}

/* Bit i moves to (i * mul) mod 63 (bit 63 stays): mul = 16 forward, 4 inverse. */
template <int mul>
inline uint64_t p_layer(uint64_t state) {
    uint64_t out = 0;
    for (int i = 0; i < 64; i++) {
        const uint64_t bit = (state >> i) & 1ULL;
        const int dest = (i == 63) ? 63 : (i * mul) % 63;
        out |= (bit << dest);
    }
    return out;
}

static_assert(sizeof(lwc_present80_key_t) == kRoundKeys * sizeof(uint64_t), "key layout");

} // namespace

extern "C" int32_t lwc_cpp_present80_init(lwc_present80_key_t *ctx, const uint8_t *key) {
    if (ctx == nullptr || key == nullptr) {
        return LWC_ERR_NULL_PTR;
    }

    uint16_t k_hi = static_cast<uint16_t>((key[0] << 8) | key[1]);
    uint64_t k_lo = load64_be(key + 2);

    for (int round = 0; round < kRoundKeys; round++) {
        /* Round key is 64 most significant bits */
        ctx->round_keys[round] = (static_cast<uint64_t>(k_hi) << 48) | (k_lo >> 16);

        if (round < kRounds) {
            /* 1. Rotate left 61 bits (rotate right 19 bits) */
            uint16_t new_hi = static_cast<uint16_t>((k_lo >> 3) & 0xFFFF);
            uint64_t new_lo = ((k_lo & 7ULL) << 61) | (static_cast<uint64_t>(k_hi) << 45) | (k_lo >> 19);

            /* 2. S-box on 4 highest bits */
            const uint8_t top_nibble = static_cast<uint8_t>(new_hi >> 12);
            new_hi = static_cast<uint16_t>((SBOX[top_nibble] << 12) | (new_hi & 0x0FFF));

            /* 3. Round counter addition on bits 19..15 */
            new_lo ^= static_cast<uint64_t>(round + 1) << 15;

            k_hi = new_hi;
            k_lo = new_lo;
        }
    }

    return LWC_SUCCESS;
}

extern "C" int32_t lwc_cpp_present80_encrypt_block(const lwc_present80_key_t *ctx, const uint8_t *pt, uint8_t *ct) {
    if (ctx == nullptr || pt == nullptr || ct == nullptr) {
        return LWC_ERR_NULL_PTR;
    }

    uint64_t state = load64_be(pt);

    for (int i = 0; i < kRounds; i++) {
        state ^= ctx->round_keys[i];
        state = sbox_layer(state, SBOX);
        state = p_layer<16>(state);
    }

    state ^= ctx->round_keys[kRounds];
    store64_be(ct, state);

    return LWC_SUCCESS;
}

extern "C" int32_t lwc_cpp_present80_decrypt_block(const lwc_present80_key_t *ctx, const uint8_t *ct, uint8_t *pt) {
    if (ctx == nullptr || ct == nullptr || pt == nullptr) {
        return LWC_ERR_NULL_PTR;
    }

    uint64_t state = load64_be(ct);

    for (int i = kRounds; i > 0; i--) {
        state ^= ctx->round_keys[i];
        state = p_layer<4>(state);
        state = sbox_layer(state, SBOX_INV);
    }

    state ^= ctx->round_keys[0];
    store64_be(pt, state);

    return LWC_SUCCESS;
}
