//! PRESENT-80 Lightweight Block Cipher Implementation in Rust (hardware-optimized)

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

#[inline(always)]
fn sbox_layer(state: u64) -> u64 {
    let mut out = 0u64;
    for i in 0..16 {
        let nibble = ((state >> (i * 4)) & 0x0F) as usize;
        let s = unsafe { *SBOX.get_unchecked(nibble) };
        out |= (s as u64) << (i * 4);
    }
    out
}

#[inline(always)]
fn sbox_layer_inv(state: u64) -> u64 {
    let mut out = 0u64;
    for i in 0..16 {
        let nibble = ((state >> (i * 4)) & 0x0F) as usize;
        let s = unsafe { *SBOX_INV.get_unchecked(nibble) };
        out |= (s as u64) << (i * 4);
    }
    out
}

#[inline(always)]
fn p_layer(state: u64) -> u64 {
    let mut out = 0u64;
    for i in 0..64 {
        let bit = (state >> i) & 1;
        let dest = if i == 63 { 63 } else { (i * 16) % 63 };
        out |= bit << dest;
    }
    out
}

#[inline(always)]
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
pub unsafe extern "C" fn lwc_rso_present80_init(
    ctx: *mut LwcPresent80Key,
    key: *const u8,
) -> i32 {
    if ctx.is_null() || key.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let k_hi = (unsafe { core::ptr::read_unaligned(key as *const u16) }).to_be();
    let k_lo = (unsafe { core::ptr::read_unaligned(key.add(2) as *const u64) }).to_be();
    let rk = unsafe { &mut (*ctx).round_keys };

    let mut hi = k_hi;
    let mut lo = k_lo;

    for round in 0..PRESENT80_ROUND_KEYS {
        unsafe {
            *rk.get_unchecked_mut(round) = ((hi as u64) << 48) | (lo >> 16);
        }

        if round < PRESENT80_ROUNDS {
            let new_hi = ((lo >> 3) & 0xFFFF) as u16;
            let mut new_lo = ((lo & 7) << 61) | ((hi as u64) << 45) | (lo >> 19);

            let top_nibble = (new_hi >> 12) as usize;
            let s = unsafe { *SBOX.get_unchecked(top_nibble) };
            let updated_hi = ((s as u16) << 12) | (new_hi & 0x0FFF);

            new_lo ^= ((round + 1) as u64) << 15;

            hi = updated_hi;
            lo = new_lo;
        }
    }

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rso_present80_encrypt_block(
    ctx: *const LwcPresent80Key,
    pt: *const u8,
    ct: *mut u8,
) -> i32 {
    if ctx.is_null() || pt.is_null() || ct.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let rk = unsafe { &(*ctx).round_keys };
    let mut state = (unsafe { core::ptr::read_unaligned(pt as *const u64) }).to_be();

    for i in 0..PRESENT80_ROUNDS {
        state ^= unsafe { *rk.get_unchecked(i) };
        state = sbox_layer(state);
        state = p_layer(state);
    }

    state ^= unsafe { *rk.get_unchecked(PRESENT80_ROUNDS) };
    unsafe {
        core::ptr::write_unaligned(ct as *mut u64, state.to_be());
    }

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rso_present80_decrypt_block(
    ctx: *const LwcPresent80Key,
    ct: *const u8,
    pt: *mut u8,
) -> i32 {
    if ctx.is_null() || ct.is_null() || pt.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let rk = unsafe { &(*ctx).round_keys };
    let mut state = (unsafe { core::ptr::read_unaligned(ct as *const u64) }).to_be();

    for i in (1..=PRESENT80_ROUNDS).rev() {
        state ^= unsafe { *rk.get_unchecked(i) };
        state = p_layer_inv(state);
        state = sbox_layer_inv(state);
    }

    state ^= unsafe { *rk.get_unchecked(0) };
    unsafe {
        core::ptr::write_unaligned(pt as *mut u64, state.to_be());
    }

    LWC_SUCCESS
}
