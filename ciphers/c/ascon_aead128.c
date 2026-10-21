/**
 * @file ascon_aead128.c
 * @brief Ascon-AEAD128 (NIST SP 800-232) C99 implementation
 *
 * 128-bit key, nonce and tag; 128-bit rate; p[12] for initialisation and
 * finalisation, p[8] for data. Bytes are loaded into 64-bit words little-endian.
 */

#include "lwc_api.h"

#define ROTR64(x, n) (((x) >> (n)) | ((x) << (64 - (n))))

#define ASCON_AEAD128_IV 0x00001000808c0001ULL
#define ASCON_DSEP       0x8000000000000000ULL

/* Round constants; p[n] uses the last n entries */
static const uint64_t RC[12] = {
    0xf0, 0xe1, 0xd2, 0xc3, 0xb4, 0xa5, 0x96, 0x87, 0x78, 0x69, 0x5a, 0x4b
};

static inline uint64_t load64_le(const uint8_t *b) {
    return ((uint64_t)b[0])         |
           (((uint64_t)b[1]) << 8)  |
           (((uint64_t)b[2]) << 16) |
           (((uint64_t)b[3]) << 24) |
           (((uint64_t)b[4]) << 32) |
           (((uint64_t)b[5]) << 40) |
           (((uint64_t)b[6]) << 48) |
           (((uint64_t)b[7]) << 56);
}

static inline void store64_le(uint8_t *b, uint64_t v) {
    b[0] = (uint8_t)(v);
    b[1] = (uint8_t)(v >> 8);
    b[2] = (uint8_t)(v >> 16);
    b[3] = (uint8_t)(v >> 24);
    b[4] = (uint8_t)(v >> 32);
    b[5] = (uint8_t)(v >> 40);
    b[6] = (uint8_t)(v >> 48);
    b[7] = (uint8_t)(v >> 56);
}

/* n < 8 bytes */
static inline uint64_t load_bytes_le(const uint8_t *b, size_t n) {
    uint64_t v = 0;
    for (size_t i = 0; i < n; i++) {
        v |= ((uint64_t)b[i]) << (8 * i);
    }
    return v;
}

static inline void store_bytes_le(uint8_t *b, uint64_t v, size_t n) {
    for (size_t i = 0; i < n; i++) {
        b[i] = (uint8_t)(v >> (8 * i));
    }
}

/* Padding bit for a partial word of n < 8 bytes */
static inline uint64_t pad(size_t n) {
    return 0x01ULL << (8 * n);
}

/* Keep the bytes above the first n (n < 8) */
static inline uint64_t clear_bytes(uint64_t x, size_t n) {
    return x & (~0ULL << (8 * n));
}

static inline void ascon_permutation(uint64_t s[5], int rounds) {
    uint64_t x0 = s[0], x1 = s[1], x2 = s[2], x3 = s[3], x4 = s[4];

    for (int i = 12 - rounds; i < 12; i++) {
        /* 1. Add round constant */
        x2 ^= RC[i];

        /* 2. Substitution layer (5-bit S-box, bitsliced) */
        x0 ^= x4; x4 ^= x3; x2 ^= x1;
        uint64_t t0 = ~x0 & x1;
        uint64_t t1 = ~x1 & x2;
        uint64_t t2 = ~x2 & x3;
        uint64_t t3 = ~x3 & x4;
        uint64_t t4 = ~x4 & x0;
        x0 ^= t1; x1 ^= t2; x2 ^= t3; x3 ^= t4; x4 ^= t0;
        x1 ^= x0; x0 ^= x4; x3 ^= x2; x2 = ~x2;

        /* 3. Linear diffusion layer */
        x0 ^= ROTR64(x0, 19) ^ ROTR64(x0, 28);
        x1 ^= ROTR64(x1, 61) ^ ROTR64(x1, 39);
        x2 ^= ROTR64(x2, 1)  ^ ROTR64(x2, 6);
        x3 ^= ROTR64(x3, 10) ^ ROTR64(x3, 17);
        x4 ^= ROTR64(x4, 7)  ^ ROTR64(x4, 41);
    }

    s[0] = x0; s[1] = x1; s[2] = x2; s[3] = x3; s[4] = x4;
}

static inline void ascon_init(uint64_t s[5], uint64_t k0, uint64_t k1, const uint8_t *nonce) {
    s[0] = ASCON_AEAD128_IV;
    s[1] = k0;
    s[2] = k1;
    s[3] = load64_le(nonce);
    s[4] = load64_le(nonce + 8);
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

static inline void ascon_absorb_ad(uint64_t s[5], const uint8_t *ad, size_t ad_len) {
    if (ad_len > 0) {
        while (ad_len >= 16) {
            s[0] ^= load64_le(ad);
            s[1] ^= load64_le(ad + 8);
            ascon_permutation(s, 8);
            ad += 16;
            ad_len -= 16;
        }
        if (ad_len >= 8) {
            s[0] ^= load64_le(ad);
            s[1] ^= load_bytes_le(ad + 8, ad_len - 8) ^ pad(ad_len - 8);
        } else {
            s[0] ^= load_bytes_le(ad, ad_len) ^ pad(ad_len);
        }
        ascon_permutation(s, 8);
    }
    s[4] ^= ASCON_DSEP; /* Domain separation */
}

static inline void ascon_finalize(uint64_t s[5], uint64_t k0, uint64_t k1) {
    s[2] ^= k0;
    s[3] ^= k1;
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

int32_t lwc_c_ascon_aead128_encrypt(
    uint8_t *ct,
    uint8_t *tag,
    const uint8_t *pt,
    size_t pt_len,
    const uint8_t *ad,
    size_t ad_len,
    const uint8_t *nonce,
    const uint8_t *key
) {
    if (!tag || !nonce || !key || (pt_len > 0 && (!pt || !ct)) || (ad_len > 0 && !ad)) {
        return LWC_ERR_NULL_PTR;
    }

    uint64_t s[5];
    uint64_t k0 = load64_le(key);
    uint64_t k1 = load64_le(key + 8);

    ascon_init(s, k0, k1, nonce);
    ascon_absorb_ad(s, ad, ad_len);

    /* Plaintext processing */
    while (pt_len >= 16) {
        s[0] ^= load64_le(pt);
        s[1] ^= load64_le(pt + 8);
        store64_le(ct, s[0]);
        store64_le(ct + 8, s[1]);
        ascon_permutation(s, 8);
        pt += 16;
        ct += 16;
        pt_len -= 16;
    }
    if (pt_len >= 8) {
        s[0] ^= load64_le(pt);
        store64_le(ct, s[0]);
        s[1] ^= load_bytes_le(pt + 8, pt_len - 8);
        store_bytes_le(ct + 8, s[1], pt_len - 8);
        s[1] ^= pad(pt_len - 8);
    } else {
        s[0] ^= load_bytes_le(pt, pt_len);
        store_bytes_le(ct, s[0], pt_len);
        s[0] ^= pad(pt_len);
    }

    ascon_finalize(s, k0, k1);
    store64_le(tag, s[3]);
    store64_le(tag + 8, s[4]);

    return LWC_SUCCESS;
}

int32_t lwc_c_ascon_aead128_decrypt(
    uint8_t *pt,
    const uint8_t *ct,
    size_t ct_len,
    const uint8_t *tag,
    const uint8_t *ad,
    size_t ad_len,
    const uint8_t *nonce,
    const uint8_t *key
) {
    if (!tag || !nonce || !key || (ct_len > 0 && (!pt || !ct)) || (ad_len > 0 && !ad)) {
        return LWC_ERR_NULL_PTR;
    }

    uint8_t *orig_pt = pt;
    size_t orig_ct_len = ct_len;

    uint64_t s[5];
    uint64_t k0 = load64_le(key);
    uint64_t k1 = load64_le(key + 8);

    ascon_init(s, k0, k1, nonce);
    ascon_absorb_ad(s, ad, ad_len);

    /* Ciphertext processing */
    while (ct_len >= 16) {
        uint64_t c0 = load64_le(ct);
        uint64_t c1 = load64_le(ct + 8);
        store64_le(pt, s[0] ^ c0);
        store64_le(pt + 8, s[1] ^ c1);
        s[0] = c0;
        s[1] = c1;
        ascon_permutation(s, 8);
        ct += 16;
        pt += 16;
        ct_len -= 16;
    }
    if (ct_len >= 8) {
        uint64_t c0 = load64_le(ct);
        store64_le(pt, s[0] ^ c0);
        s[0] = c0;
        size_t n = ct_len - 8;
        uint64_t c1 = load_bytes_le(ct + 8, n);
        store_bytes_le(pt + 8, s[1] ^ c1, n);
        s[1] = clear_bytes(s[1], n) | c1;
        s[1] ^= pad(n);
    } else {
        uint64_t c0 = load_bytes_le(ct, ct_len);
        store_bytes_le(pt, s[0] ^ c0, ct_len);
        s[0] = clear_bytes(s[0], ct_len) | c0;
        s[0] ^= pad(ct_len);
    }

    ascon_finalize(s, k0, k1);

    /* Constant-time tag check */
    uint64_t diff = (s[3] ^ load64_le(tag)) | (s[4] ^ load64_le(tag + 8));

    if (diff != 0) {
        for (size_t i = 0; i < orig_ct_len; i++) {
            orig_pt[i] = 0;
        }
        return LWC_ERR_AUTH_FAIL;
    }

    return LWC_SUCCESS;
}
