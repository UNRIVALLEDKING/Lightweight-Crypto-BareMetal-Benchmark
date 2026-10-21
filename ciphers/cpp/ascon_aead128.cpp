/**
 * @file ascon_aead128.cpp
 * @brief Ascon-AEAD128 (NIST SP 800-232), freestanding C++17 (mirrors ciphers/c/ascon_aead128.c)
 */

#include "lwc_cpp_util.hpp"

namespace {

using lwc::detail::load64_le;
using lwc::detail::rotr;
using lwc::detail::store64_le;

constexpr uint64_t ASCON_AEAD128_IV = 0x00001000808c0001ULL;
constexpr uint64_t ASCON_DSEP       = 0x8000000000000000ULL;

/* Round constants; p[n] uses the last n entries */
constexpr uint64_t RC[12] = {
    0xf0, 0xe1, 0xd2, 0xc3, 0xb4, 0xa5, 0x96, 0x87, 0x78, 0x69, 0x5a, 0x4b
};

/* n < 8 bytes */
inline uint64_t load_bytes_le(const uint8_t *b, size_t n) {
    uint64_t v = 0;
    for (size_t i = 0; i < n; i++) {
        v |= static_cast<uint64_t>(b[i]) << (8 * i);
    }
    return v;
}

inline void store_bytes_le(uint8_t *b, uint64_t v, size_t n) {
    for (size_t i = 0; i < n; i++) {
        b[i] = static_cast<uint8_t>(v >> (8 * i));
    }
}

/* Padding bit for a partial word of n < 8 bytes */
constexpr uint64_t pad(size_t n) {
    return 0x01ULL << (8 * n);
}

/* Keep the bytes above the first n (n < 8) */
constexpr uint64_t clear_bytes(uint64_t x, size_t n) {
    return x & (~0ULL << (8 * n));
}

struct AsconState {
    uint64_t x[5];

    inline void permute(int rounds) {
        uint64_t x0 = x[0], x1 = x[1], x2 = x[2], x3 = x[3], x4 = x[4];

        for (int i = 12 - rounds; i < 12; i++) {
            /* 1. Add round constant */
            x2 ^= RC[i];

            /* 2. Substitution layer (5-bit S-box, bitsliced) */
            x0 ^= x4; x4 ^= x3; x2 ^= x1;
            const uint64_t t0 = ~x0 & x1;
            const uint64_t t1 = ~x1 & x2;
            const uint64_t t2 = ~x2 & x3;
            const uint64_t t3 = ~x3 & x4;
            const uint64_t t4 = ~x4 & x0;
            x0 ^= t1; x1 ^= t2; x2 ^= t3; x3 ^= t4; x4 ^= t0;
            x1 ^= x0; x0 ^= x4; x3 ^= x2; x2 = ~x2;

            /* 3. Linear diffusion layer */
            x0 ^= rotr(x0, 19) ^ rotr(x0, 28);
            x1 ^= rotr(x1, 61) ^ rotr(x1, 39);
            x2 ^= rotr(x2, 1)  ^ rotr(x2, 6);
            x3 ^= rotr(x3, 10) ^ rotr(x3, 17);
            x4 ^= rotr(x4, 7)  ^ rotr(x4, 41);
        }

        x[0] = x0; x[1] = x1; x[2] = x2; x[3] = x3; x[4] = x4;
    }

    inline void init(uint64_t k0, uint64_t k1, const uint8_t *nonce) {
        x[0] = ASCON_AEAD128_IV;
        x[1] = k0;
        x[2] = k1;
        x[3] = load64_le(nonce);
        x[4] = load64_le(nonce + 8);
        permute(12);
        x[3] ^= k0;
        x[4] ^= k1;
    }

    inline void absorb_ad(const uint8_t *ad, size_t ad_len) {
        if (ad_len > 0) {
            while (ad_len >= 16) {
                x[0] ^= load64_le(ad);
                x[1] ^= load64_le(ad + 8);
                permute(8);
                ad += 16;
                ad_len -= 16;
            }
            if (ad_len >= 8) {
                x[0] ^= load64_le(ad);
                x[1] ^= load_bytes_le(ad + 8, ad_len - 8) ^ pad(ad_len - 8);
            } else {
                x[0] ^= load_bytes_le(ad, ad_len) ^ pad(ad_len);
            }
            permute(8);
        }
        x[4] ^= ASCON_DSEP; /* Domain separation */
    }

    inline void finalize(uint64_t k0, uint64_t k1) {
        x[2] ^= k0;
        x[3] ^= k1;
        permute(12);
        x[3] ^= k0;
        x[4] ^= k1;
    }
};

} // namespace

extern "C" int32_t lwc_cpp_ascon_aead128_encrypt(
    uint8_t *ct,
    uint8_t *tag,
    const uint8_t *pt,
    size_t pt_len,
    const uint8_t *ad,
    size_t ad_len,
    const uint8_t *nonce,
    const uint8_t *key
) {
    if (tag == nullptr || nonce == nullptr || key == nullptr ||
        (pt_len > 0 && (pt == nullptr || ct == nullptr)) || (ad_len > 0 && ad == nullptr)) {
        return LWC_ERR_NULL_PTR;
    }

    AsconState s;
    const uint64_t k0 = load64_le(key);
    const uint64_t k1 = load64_le(key + 8);

    s.init(k0, k1, nonce);
    s.absorb_ad(ad, ad_len);

    /* Plaintext processing */
    while (pt_len >= 16) {
        s.x[0] ^= load64_le(pt);
        s.x[1] ^= load64_le(pt + 8);
        store64_le(ct, s.x[0]);
        store64_le(ct + 8, s.x[1]);
        s.permute(8);
        pt += 16;
        ct += 16;
        pt_len -= 16;
    }
    if (pt_len >= 8) {
        s.x[0] ^= load64_le(pt);
        store64_le(ct, s.x[0]);
        s.x[1] ^= load_bytes_le(pt + 8, pt_len - 8);
        store_bytes_le(ct + 8, s.x[1], pt_len - 8);
        s.x[1] ^= pad(pt_len - 8);
    } else {
        s.x[0] ^= load_bytes_le(pt, pt_len);
        store_bytes_le(ct, s.x[0], pt_len);
        s.x[0] ^= pad(pt_len);
    }

    s.finalize(k0, k1);
    store64_le(tag, s.x[3]);
    store64_le(tag + 8, s.x[4]);

    return LWC_SUCCESS;
}

extern "C" int32_t lwc_cpp_ascon_aead128_decrypt(
    uint8_t *pt,
    const uint8_t *ct,
    size_t ct_len,
    const uint8_t *tag,
    const uint8_t *ad,
    size_t ad_len,
    const uint8_t *nonce,
    const uint8_t *key
) {
    if (tag == nullptr || nonce == nullptr || key == nullptr ||
        (ct_len > 0 && (pt == nullptr || ct == nullptr)) || (ad_len > 0 && ad == nullptr)) {
        return LWC_ERR_NULL_PTR;
    }

    uint8_t *const orig_pt = pt;
    const size_t orig_ct_len = ct_len;

    AsconState s;
    const uint64_t k0 = load64_le(key);
    const uint64_t k1 = load64_le(key + 8);

    s.init(k0, k1, nonce);
    s.absorb_ad(ad, ad_len);

    /* Ciphertext processing */
    while (ct_len >= 16) {
        const uint64_t c0 = load64_le(ct);
        const uint64_t c1 = load64_le(ct + 8);
        store64_le(pt, s.x[0] ^ c0);
        store64_le(pt + 8, s.x[1] ^ c1);
        s.x[0] = c0;
        s.x[1] = c1;
        s.permute(8);
        ct += 16;
        pt += 16;
        ct_len -= 16;
    }
    if (ct_len >= 8) {
        const uint64_t c0 = load64_le(ct);
        store64_le(pt, s.x[0] ^ c0);
        s.x[0] = c0;
        const size_t n = ct_len - 8;
        const uint64_t c1 = load_bytes_le(ct + 8, n);
        store_bytes_le(pt + 8, s.x[1] ^ c1, n);
        s.x[1] = clear_bytes(s.x[1], n) | c1;
        s.x[1] ^= pad(n);
    } else {
        const uint64_t c0 = load_bytes_le(ct, ct_len);
        store_bytes_le(pt, s.x[0] ^ c0, ct_len);
        s.x[0] = clear_bytes(s.x[0], ct_len) | c0;
        s.x[0] ^= pad(ct_len);
    }

    s.finalize(k0, k1);

    /* Constant-time tag check */
    const uint64_t diff = (s.x[3] ^ load64_le(tag)) | (s.x[4] ^ load64_le(tag + 8));

    if (diff != 0) {
        for (size_t i = 0; i < orig_ct_len; i++) {
            orig_pt[i] = 0;
        }
        return LWC_ERR_AUTH_FAIL;
    }

    return LWC_SUCCESS;
}
