//! PRESENT-80 Lightweight Block Cipher Implementation in Rust (no_std)

use crate::{LWC_ERR_NULL_PTR, LWC_SUCCESS};

pub const PRESENT80_ROUNDS: usize = 31;
pub const PRESENT80_ROUND_KEYS: usize = 32;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct LwcPresent80Key {
    pub round_keys: [u64; PRESENT80_ROUND_KEYS],
}

const SBOX: [u8; 16] = [
    0xC, 0x5, 0x6, 0xB, 0x9, 0x0, 0xA, 0xD,
    0x3, 0xE, 0xF, 0x8, 0x4, 0x7, 0x1, 0x2,
];

const SBOX_INV: [u8; 16] = [
    0x5, 0xE, 0xF, 0x8, 0xC, 0x1, 0x2, 0xD,
    0xB, 0x4, 0x6, 0x3, 0x0, 0x7, 0x9, 0xA,
];

#[inline]
fn sbox_layer(state: u64) -> u64 {
    let mut out = 0u64;
    for i in 0..16 {
        let nibble = ((state >> (i * 4)) & 0x0F) as usize;
        out |= (SBOX[nibble] as u64) << (i * 4);
    }
    out
}

#[inline]
fn sbox_layer_inv(state: u64) -> u64 {
    let mut out = 0u64;
    for i in 0..16 {
        let nibble = ((state >> (i * 4)) & 0x0F) as usize;
        out |= (SBOX_INV[nibble] as u64) << (i * 4);
    }
    out
}

#[inline]
fn p_layer(state: u64) -> u64 {
    let mut out = 0u64;
    for i in 0..64 {
        let bit = (state >> i) & 1;
        let dest = if i == 63 { 63 } else { (i * 16) % 63 };
        out |= bit << dest;
    }
    out
}

#[inline]
fn p_layer_inv(state: u64) -> u64 {
    let mut out = 0u64;
    for i in 0..64 {
        let bit = (state >> i) & 1;
        let dest = if i == 63 { 63 } else { (i * 4) % 63 };
        out |= bit << dest;
    }
    out
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_present80_init(
    ctx: *mut LwcPresent80Key,
    key: *const u8,
) -> i32 {
    if ctx.is_null() || key.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let key_slice = unsafe { core::slice::from_raw_parts(key, 10) };
    let ctx_ref = unsafe { &mut *ctx };

    let mut k_hi = u16::from_be_bytes([key_slice[0], key_slice[1]]);
    let mut k_lo = u64::from_be_bytes([
        key_slice[2], key_slice[3], key_slice[4], key_slice[5],
        key_slice[6], key_slice[7], key_slice[8], key_slice[9],
    ]);

    for round in 0..PRESENT80_ROUND_KEYS {
        ctx_ref.round_keys[round] = ((k_hi as u64) << 48) | (k_lo >> 16);

        if round < PRESENT80_ROUNDS {
            let new_hi = ((k_lo >> 3) & 0xFFFF) as u16;
            let mut new_lo = ((k_lo & 7) << 61) | ((k_hi as u64) << 45) | (k_lo >> 19);

            let top_nibble = (new_hi >> 12) as usize;
            let updated_hi = ((SBOX[top_nibble] as u16) << 12) | (new_hi & 0x0FFF);

            new_lo ^= ((round + 1) as u64) << 15;

            k_hi = updated_hi;
            k_lo = new_lo;
        }
    }

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_present80_encrypt_block(
    ctx: *const LwcPresent80Key,
    pt: *const u8,
    ct: *mut u8,
) -> i32 {
    if ctx.is_null() || pt.is_null() || ct.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let ctx_ref = unsafe { &*ctx };
    let pt_slice = unsafe { core::slice::from_raw_parts(pt, 8) };
    let ct_slice = unsafe { core::slice::from_raw_parts_mut(ct, 8) };

    let mut state = u64::from_be_bytes([
        pt_slice[0], pt_slice[1], pt_slice[2], pt_slice[3],
        pt_slice[4], pt_slice[5], pt_slice[6], pt_slice[7],
    ]);

    for i in 0..PRESENT80_ROUNDS {
        state ^= ctx_ref.round_keys[i];
        state = sbox_layer(state);
        state = p_layer(state);
    }

    state ^= ctx_ref.round_keys[PRESENT80_ROUNDS];
    ct_slice.copy_from_slice(&state.to_be_bytes());

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_present80_decrypt_block(
    ctx: *const LwcPresent80Key,
    ct: *const u8,
    pt: *mut u8,
) -> i32 {
    if ctx.is_null() || ct.is_null() || pt.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let ctx_ref = unsafe { &*ctx };
    let ct_slice = unsafe { core::slice::from_raw_parts(ct, 8) };
    let pt_slice = unsafe { core::slice::from_raw_parts_mut(pt, 8) };

    let mut state = u64::from_be_bytes([
        ct_slice[0], ct_slice[1], ct_slice[2], ct_slice[3],
        ct_slice[4], ct_slice[5], ct_slice[6], ct_slice[7],
    ]);

    for i in (1..=PRESENT80_ROUNDS).rev() {
        state ^= ctx_ref.round_keys[i];
        state = p_layer_inv(state);
        state = sbox_layer_inv(state);
    }

    state ^= ctx_ref.round_keys[0];
    pt_slice.copy_from_slice(&state.to_be_bytes());

    LWC_SUCCESS
}
