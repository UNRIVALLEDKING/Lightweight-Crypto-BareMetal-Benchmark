/**
 * @file simon64_128.cpp
 * @brief NSA SIMON 64/128 block cipher, freestanding C++17 (mirrors ciphers/c/simon64_128.c)
 */

#include "lwc_cpp_util.hpp"

namespace {

using lwc::detail::load32_le;
using lwc::detail::rotl;
using lwc::detail::rotr;
using lwc::detail::store32_le;

constexpr int kRounds = LWC_SIMON64_128_ROUNDS;

/* 62-bit z3 constant sequence for SIMON 64/128 */
constexpr uint8_t Z3[62] = {
    1,1,0,1,1,0,1,1,1,0,1,0,1,1,0,0,0,1,1,0,0,1,0,1,1,1,1,0,0,0,
    0,0,0,1,0,0,1,0,0,0,1,0,1,0,0,1,1,1,0,0,1,1,0,1,0,0,0,0,1,1,1,1
};

constexpr uint32_t simon_f(uint32_t x) {
    return (rotl(x, 1) & rotl(x, 8)) ^ rotl(x, 2);
}

static_assert(sizeof(lwc_simon64_128_key_t) == kRounds * sizeof(uint32_t), "key layout");

} // namespace

extern "C" int32_t lwc_cpp_simon64_128_init(lwc_simon64_128_key_t *ctx, const uint8_t *key) {
    if (ctx == nullptr || key == nullptr) {
        return LWC_ERR_NULL_PTR;
    }

    uint32_t *rk = ctx->round_keys;
    rk[0] = load32_le(key + 0);
    rk[1] = load32_le(key + 4);
    rk[2] = load32_le(key + 8);
    rk[3] = load32_le(key + 12);

    for (int i = 4; i < kRounds; i++) {
        uint32_t tmp = rotr(rk[i - 1], 3);
        tmp ^= rk[i - 3];
        tmp ^= rotr(tmp, 1);
        rk[i] = ~rk[i - 4] ^ tmp ^ Z3[(i - 4) % 62] ^ 3u;
    }

    return LWC_SUCCESS;
}

extern "C" int32_t lwc_cpp_simon64_128_encrypt_block(const lwc_simon64_128_key_t *ctx, const uint8_t *pt, uint8_t *ct) {
    if (ctx == nullptr || pt == nullptr || ct == nullptr) {
        return LWC_ERR_NULL_PTR;
    }

    uint32_t x = load32_le(pt + 4);
    uint32_t y = load32_le(pt + 0);

    for (int i = 0; i < kRounds; i++) {
        const uint32_t tmp = simon_f(x) ^ y ^ ctx->round_keys[i];
        y = x;
        x = tmp;
    }

    store32_le(ct + 4, x);
    store32_le(ct + 0, y);

    return LWC_SUCCESS;
}

extern "C" int32_t lwc_cpp_simon64_128_decrypt_block(const lwc_simon64_128_key_t *ctx, const uint8_t *ct, uint8_t *pt) {
    if (ctx == nullptr || ct == nullptr || pt == nullptr) {
        return LWC_ERR_NULL_PTR;
    }

    uint32_t x = load32_le(ct + 4);
    uint32_t y = load32_le(ct + 0);

    for (int i = kRounds - 1; i >= 0; i--) {
        const uint32_t tmp = simon_f(y) ^ x ^ ctx->round_keys[i];
        x = y;
        y = tmp;
    }

    store32_le(pt + 4, x);
    store32_le(pt + 0, y);

    return LWC_SUCCESS;
}
