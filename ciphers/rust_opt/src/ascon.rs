//! Ascon-AEAD128 (NIST SP 800-232) implementation in Rust (hardware-optimized)

use crate::{LWC_ERR_AUTH_FAIL, LWC_ERR_NULL_PTR, LWC_SUCCESS};

const ASCON_AEAD128_IV: u64 = 0x0000_1000_808c_0001;
const ASCON_DSEP: u64 = 0x8000_0000_0000_0000;

const RC: [u64; 12] = [
    0xf0, 0xe1, 0xd2, 0xc3, 0xb4, 0xa5, 0x96, 0x87, 0x78, 0x69, 0x5a, 0x4b,
];

#[inline]
unsafe fn load64_le(ptr: *const u8) -> u64 {
    u64::from_le(core::ptr::read_unaligned(ptr as *const u64))
}

#[inline]
unsafe fn store64_le(ptr: *mut u8, v: u64) {
    core::ptr::write_unaligned(ptr as *mut u64, v.to_le());
}

#[inline]
unsafe fn load_bytes_le(ptr: *const u8, len: usize) -> u64 {
    let mut v = 0u64;
    for i in 0..len {
        v |= (*ptr.add(i) as u64) << (8 * i);
    }
    v
}

#[inline]
unsafe fn store_bytes_le(ptr: *mut u8, v: u64, len: usize) {
    for i in 0..len {
        *ptr.add(i) = (v >> (8 * i)) as u8;
    }
}

#[inline]
fn pad(n: usize) -> u64 {
    0x01u64 << (8 * n)
}

#[inline]
fn clear_bytes(x: u64, n: usize) -> u64 {
    x & (!0u64 << (8 * n))
}

#[inline]
fn ascon_permutation(s: &mut [u64; 5], rounds: usize) {
    let [mut x0, mut x1, mut x2, mut x3, mut x4] = *s;

    for i in (12 - rounds)..12 {
        x2 ^= unsafe { *RC.get_unchecked(i) };

        x0 ^= x4; x4 ^= x3; x2 ^= x1;
        let t0 = !x0 & x1;
        let t1 = !x1 & x2;
        let t2 = !x2 & x3;
        let t3 = !x3 & x4;
        let t4 = !x4 & x0;
        x0 ^= t1; x1 ^= t2; x2 ^= t3; x3 ^= t4; x4 ^= t0;
        x1 ^= x0; x0 ^= x4; x3 ^= x2; x2 = !x2;

        x0 ^= x0.rotate_right(19) ^ x0.rotate_right(28);
        x1 ^= x1.rotate_right(61) ^ x1.rotate_right(39);
        x2 ^= x2.rotate_right(1)  ^ x2.rotate_right(6);
        x3 ^= x3.rotate_right(10) ^ x3.rotate_right(17);
        x4 ^= x4.rotate_right(7)  ^ x4.rotate_right(41);
    }

    *s = [x0, x1, x2, x3, x4];
}

#[inline]
unsafe fn ascon_init(s: &mut [u64; 5], k0: u64, k1: u64, nonce: *const u8) {
    *s = [ASCON_AEAD128_IV, k0, k1, load64_le(nonce), load64_le(nonce.add(8))];
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

#[inline]
unsafe fn ascon_absorb_ad(s: &mut [u64; 5], mut ad: *const u8, mut ad_len: usize) {
    if ad_len > 0 {
        while ad_len >= 16 {
            s[0] ^= load64_le(ad);
            s[1] ^= load64_le(ad.add(8));
            ascon_permutation(s, 8);
            ad = ad.add(16);
            ad_len -= 16;
        }
        if ad_len >= 8 {
            s[0] ^= load64_le(ad);
            s[1] ^= load_bytes_le(ad.add(8), ad_len - 8) ^ pad(ad_len - 8);
        } else {
            s[0] ^= load_bytes_le(ad, ad_len) ^ pad(ad_len);
        }
        ascon_permutation(s, 8);
    }
    s[4] ^= ASCON_DSEP;
}

#[inline]
fn ascon_finalize(s: &mut [u64; 5], k0: u64, k1: u64) {
    s[2] ^= k0;
    s[3] ^= k1;
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rso_ascon_aead128_encrypt(
    mut ct: *mut u8,
    tag: *mut u8,
    mut pt: *const u8,
    mut pt_len: usize,
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

    let mut s = [0u64; 5];
    let k0 = load64_le(key);
    let k1 = load64_le(key.add(8));

    ascon_init(&mut s, k0, k1, nonce);
    ascon_absorb_ad(&mut s, ad, ad_len);

    while pt_len >= 16 {
        s[0] ^= load64_le(pt);
        s[1] ^= load64_le(pt.add(8));
        store64_le(ct, s[0]);
        store64_le(ct.add(8), s[1]);
        ascon_permutation(&mut s, 8);
        pt = pt.add(16);
        ct = ct.add(16);
        pt_len -= 16;
    }
    if pt_len >= 8 {
        let n = pt_len - 8;
        s[0] ^= load64_le(pt);
        store64_le(ct, s[0]);
        s[1] ^= load_bytes_le(pt.add(8), n);
        store_bytes_le(ct.add(8), s[1], n);
        s[1] ^= pad(n);
    } else {
        s[0] ^= load_bytes_le(pt, pt_len);
        store_bytes_le(ct, s[0], pt_len);
        s[0] ^= pad(pt_len);
    }

    ascon_finalize(&mut s, k0, k1);
    store64_le(tag, s[3]);
    store64_le(tag.add(8), s[4]);

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rso_ascon_aead128_decrypt(
    mut pt: *mut u8,
    mut ct: *const u8,
    mut ct_len: usize,
    tag: *const u8,
    ad: *const u8,
    ad_len: usize,
    nonce: *const u8,
    key: *const u8,
) -> i32 {
    if tag.is_null() || nonce.is_null() || key.is_null() {
        return LWC_ERR_NULL_PTR;
    }
    if ct_len > 0 && (ct.is_null() || pt.is_null()) {
        return LWC_ERR_NULL_PTR;
    }
    if ad_len > 0 && ad.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let orig_pt = pt;
    let orig_len = ct_len;

    let mut s = [0u64; 5];
    let k0 = load64_le(key);
    let k1 = load64_le(key.add(8));

    ascon_init(&mut s, k0, k1, nonce);
    ascon_absorb_ad(&mut s, ad, ad_len);

    while ct_len >= 16 {
        let c0 = load64_le(ct);
        let c1 = load64_le(ct.add(8));
        store64_le(pt, s[0] ^ c0);
        store64_le(pt.add(8), s[1] ^ c1);
        s[0] = c0;
        s[1] = c1;
        ascon_permutation(&mut s, 8);
        ct = ct.add(16);
        pt = pt.add(16);
        ct_len -= 16;
    }
    if ct_len >= 8 {
        let n = ct_len - 8;
        let c0 = load64_le(ct);
        store64_le(pt, s[0] ^ c0);
        s[0] = c0;
        let c1 = load_bytes_le(ct.add(8), n);
        store_bytes_le(pt.add(8), s[1] ^ c1, n);
        s[1] = clear_bytes(s[1], n) | c1;
        s[1] ^= pad(n);
    } else {
        let c0 = load_bytes_le(ct, ct_len);
        store_bytes_le(pt, s[0] ^ c0, ct_len);
        s[0] = clear_bytes(s[0], ct_len) | c0;
        s[0] ^= pad(ct_len);
    }

    ascon_finalize(&mut s, k0, k1);

    let t0 = load64_le(tag);
    let t1 = load64_le(tag.add(8));
    let diff = (s[3] ^ t0) | (s[4] ^ t1);

    if diff != 0 {
        if !orig_pt.is_null() && orig_len > 0 {
            core::ptr::write_bytes(orig_pt, 0, orig_len);
        }
        return LWC_ERR_AUTH_FAIL;
    }

    LWC_SUCCESS
}
