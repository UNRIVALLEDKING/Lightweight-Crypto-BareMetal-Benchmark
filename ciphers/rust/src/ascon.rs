//! Ascon-AEAD128 (NIST SP 800-232) implementation in Rust (no_std)
//!
//! 128-bit key, nonce and tag; 128-bit rate; p[12] for initialisation and
//! finalisation, p[8] for data. Bytes are loaded into 64-bit words little-endian.

use crate::{LWC_ERR_AUTH_FAIL, LWC_ERR_NULL_PTR, LWC_SUCCESS};

const ASCON_AEAD128_IV: u64 = 0x0000_1000_808c_0001;
const ASCON_DSEP: u64 = 0x8000_0000_0000_0000;

/// Round constants; p[n] uses the last n entries.
const RC: [u64; 12] = [
    0xf0, 0xe1, 0xd2, 0xc3, 0xb4, 0xa5, 0x96, 0x87, 0x78, 0x69, 0x5a, 0x4b,
];

#[inline]
fn load64_le(b: &[u8]) -> u64 {
    u64::from_le_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]])
}

#[inline]
fn store64_le(b: &mut [u8], v: u64) {
    b[..8].copy_from_slice(&v.to_le_bytes());
}

/// `b.len() < 8`
#[inline]
fn load_bytes_le(b: &[u8]) -> u64 {
    let mut v = 0u64;
    for (i, &byte) in b.iter().enumerate() {
        v |= (byte as u64) << (8 * i);
    }
    v
}

#[inline]
fn store_bytes_le(b: &mut [u8], v: u64) {
    for (i, byte) in b.iter_mut().enumerate() {
        *byte = (v >> (8 * i)) as u8;
    }
}

/// Padding bit for a partial word of n < 8 bytes.
#[inline]
fn pad(n: usize) -> u64 {
    0x01u64 << (8 * n)
}

/// Keep the bytes above the first n (n < 8).
#[inline]
fn clear_bytes(x: u64, n: usize) -> u64 {
    x & (!0u64 << (8 * n))
}

#[inline]
fn ascon_permutation(s: &mut [u64; 5], rounds: usize) {
    let [mut x0, mut x1, mut x2, mut x3, mut x4] = *s;

    for i in (12 - rounds)..12 {
        // 1. Round constant
        x2 ^= RC[i];

        // 2. Bit-sliced S-box
        x0 ^= x4; x4 ^= x3; x2 ^= x1;
        let t0 = !x0 & x1;
        let t1 = !x1 & x2;
        let t2 = !x2 & x3;
        let t3 = !x3 & x4;
        let t4 = !x4 & x0;
        x0 ^= t1; x1 ^= t2; x2 ^= t3; x3 ^= t4; x4 ^= t0;
        x1 ^= x0; x0 ^= x4; x3 ^= x2; x2 = !x2;

        // 3. Linear diffusion
        x0 ^= x0.rotate_right(19) ^ x0.rotate_right(28);
        x1 ^= x1.rotate_right(61) ^ x1.rotate_right(39);
        x2 ^= x2.rotate_right(1)  ^ x2.rotate_right(6);
        x3 ^= x3.rotate_right(10) ^ x3.rotate_right(17);
        x4 ^= x4.rotate_right(7)  ^ x4.rotate_right(41);
    }

    *s = [x0, x1, x2, x3, x4];
}

#[inline]
fn ascon_init(s: &mut [u64; 5], k0: u64, k1: u64, nonce: &[u8]) {
    *s = [ASCON_AEAD128_IV, k0, k1, load64_le(&nonce[0..8]), load64_le(&nonce[8..16])];
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

#[inline]
fn ascon_absorb_ad(s: &mut [u64; 5], mut ad: &[u8]) {
    if !ad.is_empty() {
        while ad.len() >= 16 {
            s[0] ^= load64_le(&ad[0..8]);
            s[1] ^= load64_le(&ad[8..16]);
            ascon_permutation(s, 8);
            ad = &ad[16..];
        }
        if ad.len() >= 8 {
            s[0] ^= load64_le(&ad[0..8]);
            s[1] ^= load_bytes_le(&ad[8..]) ^ pad(ad.len() - 8);
        } else {
            s[0] ^= load_bytes_le(ad) ^ pad(ad.len());
        }
        ascon_permutation(s, 8);
    }
    s[4] ^= ASCON_DSEP; // Domain separation
}

#[inline]
fn ascon_finalize(s: &mut [u64; 5], k0: u64, k1: u64) {
    s[2] ^= k0;
    s[3] ^= k1;
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

/// A slice that is empty (instead of built from a null pointer) when `len == 0`.
#[inline]
unsafe fn in_slice<'a>(p: *const u8, len: usize) -> &'a [u8] {
    if len == 0 { &[] } else { unsafe { core::slice::from_raw_parts(p, len) } }
}

#[inline]
unsafe fn out_slice<'a>(p: *mut u8, len: usize) -> &'a mut [u8] {
    if len == 0 { &mut [] } else { unsafe { core::slice::from_raw_parts_mut(p, len) } }
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_ascon_aead128_encrypt(
    ct: *mut u8,
    tag: *mut u8,
    pt: *const u8,
    pt_len: usize,
    ad: *const u8,
    ad_len: usize,
    nonce: *const u8,
    key: *const u8,
) -> i32 {
    if tag.is_null() || nonce.is_null() || key.is_null() {
        return LWC_ERR_NULL_PTR;
    }
    if pt_len > 0 && (pt.is_null() || ct.is_null()) {
        return LWC_ERR_NULL_PTR;
    }
    if ad_len > 0 && ad.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let key = unsafe { core::slice::from_raw_parts(key, 16) };
    let nonce = unsafe { core::slice::from_raw_parts(nonce, 16) };
    let tag = unsafe { core::slice::from_raw_parts_mut(tag, 16) };
    let mut pt = unsafe { in_slice(pt, pt_len) };
    let mut ct = unsafe { out_slice(ct, pt_len) };
    let ad = unsafe { in_slice(ad, ad_len) };

    let mut s = [0u64; 5];
    let k0 = load64_le(&key[0..8]);
    let k1 = load64_le(&key[8..16]);

    ascon_init(&mut s, k0, k1, nonce);
    ascon_absorb_ad(&mut s, ad);

    // Plaintext processing
    while pt.len() >= 16 {
        s[0] ^= load64_le(&pt[0..8]);
        s[1] ^= load64_le(&pt[8..16]);
        store64_le(&mut ct[0..8], s[0]);
        store64_le(&mut ct[8..16], s[1]);
        ascon_permutation(&mut s, 8);
        pt = &pt[16..];
        ct = &mut core::mem::take(&mut ct)[16..];
    }
    if pt.len() >= 8 {
        let n = pt.len() - 8;
        s[0] ^= load64_le(&pt[0..8]);
        store64_le(&mut ct[0..8], s[0]);
        s[1] ^= load_bytes_le(&pt[8..]);
        store_bytes_le(&mut ct[8..], s[1]);
        s[1] ^= pad(n);
    } else {
        s[0] ^= load_bytes_le(pt);
        store_bytes_le(ct, s[0]);
        s[0] ^= pad(pt.len());
    }

    ascon_finalize(&mut s, k0, k1);
    store64_le(&mut tag[0..8], s[3]);
    store64_le(&mut tag[8..16], s[4]);

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_ascon_aead128_decrypt(
    pt: *mut u8,
    ct: *const u8,
    ct_len: usize,
    tag: *const u8,
    ad: *const u8,
    ad_len: usize,
    nonce: *const u8,
    key: *const u8,
) -> i32 {
    if tag.is_null() || nonce.is_null() || key.is_null() {
        return LWC_ERR_NULL_PTR;
    }
    if ct_len > 0 && (pt.is_null() || ct.is_null()) {
        return LWC_ERR_NULL_PTR;
    }
    if ad_len > 0 && ad.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let key = unsafe { core::slice::from_raw_parts(key, 16) };
    let nonce = unsafe { core::slice::from_raw_parts(nonce, 16) };
    let tag = unsafe { core::slice::from_raw_parts(tag, 16) };
    let mut ct = unsafe { in_slice(ct, ct_len) };
    let mut out = unsafe { out_slice(pt, ct_len) };
    let ad = unsafe { in_slice(ad, ad_len) };

    let mut s = [0u64; 5];
    let k0 = load64_le(&key[0..8]);
    let k1 = load64_le(&key[8..16]);

    ascon_init(&mut s, k0, k1, nonce);
    ascon_absorb_ad(&mut s, ad);

    // Ciphertext processing
    while ct.len() >= 16 {
        let c0 = load64_le(&ct[0..8]);
        let c1 = load64_le(&ct[8..16]);
        store64_le(&mut out[0..8], s[0] ^ c0);
        store64_le(&mut out[8..16], s[1] ^ c1);
        s[0] = c0;
        s[1] = c1;
        ascon_permutation(&mut s, 8);
        ct = &ct[16..];
        out = &mut core::mem::take(&mut out)[16..];
    }
    if ct.len() >= 8 {
        let n = ct.len() - 8;
        let c0 = load64_le(&ct[0..8]);
        store64_le(&mut out[0..8], s[0] ^ c0);
        s[0] = c0;
        let c1 = load_bytes_le(&ct[8..]);
        store_bytes_le(&mut out[8..], s[1] ^ c1);
        s[1] = clear_bytes(s[1], n) | c1;
        s[1] ^= pad(n);
    } else {
        let n = ct.len();
        let c0 = load_bytes_le(ct);
        store_bytes_le(out, s[0] ^ c0);
        s[0] = clear_bytes(s[0], n) | c0;
        s[0] ^= pad(n);
    }

    ascon_finalize(&mut s, k0, k1);

    // Constant-time tag check
    let diff = (s[3] ^ load64_le(&tag[0..8])) | (s[4] ^ load64_le(&tag[8..16]));

    if diff != 0 {
        let all = unsafe { out_slice(pt, ct_len) };
        for byte in all.iter_mut() {
            *byte = 0;
        }
        return LWC_ERR_AUTH_FAIL;
    }

    LWC_SUCCESS
}
