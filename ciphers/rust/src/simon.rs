//! SIMON 64/128 Block Cipher Implementation in Rust (no_std)

use crate::{LWC_ERR_NULL_PTR, LWC_SUCCESS};

pub const SIMON64_128_ROUNDS: usize = 44;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct LwcSimon64128Key {
    pub round_keys: [u32; SIMON64_128_ROUNDS],
}

const Z3: [u8; 62] = [
    1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0,
    0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0, 1, 1, 1, 1,
];

#[inline]
fn simon_f(x: u32) -> u32 {
    (x.rotate_left(1) & x.rotate_left(8)) ^ x.rotate_left(2)
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_simon64_128_init(
    ctx: *mut LwcSimon64128Key,
    key: *const u8,
) -> i32 {
    if ctx.is_null() || key.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let key_slice = unsafe { core::slice::from_raw_parts(key, 16) };
    let ctx_ref = unsafe { &mut *ctx };

    ctx_ref.round_keys[0] = u32::from_le_bytes([key_slice[0], key_slice[1], key_slice[2], key_slice[3]]);
    ctx_ref.round_keys[1] = u32::from_le_bytes([key_slice[4], key_slice[5], key_slice[6], key_slice[7]]);
    ctx_ref.round_keys[2] = u32::from_le_bytes([key_slice[8], key_slice[9], key_slice[10], key_slice[11]]);
    ctx_ref.round_keys[3] = u32::from_le_bytes([key_slice[12], key_slice[13], key_slice[14], key_slice[15]]);

    for i in 4..SIMON64_128_ROUNDS {
        let mut tmp = ctx_ref.round_keys[i - 1].rotate_right(3);
        tmp ^= ctx_ref.round_keys[i - 3];
        tmp ^= tmp.rotate_right(1);
        ctx_ref.round_keys[i] = !ctx_ref.round_keys[i - 4] ^ tmp ^ (Z3[(i - 4) % 62] as u32) ^ 3;
    }

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_simon64_128_encrypt_block(
    ctx: *const LwcSimon64128Key,
    pt: *const u8,
    ct: *mut u8,
) -> i32 {
    if ctx.is_null() || pt.is_null() || ct.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let ctx_ref = unsafe { &*ctx };
    let pt_slice = unsafe { core::slice::from_raw_parts(pt, 8) };
    let ct_slice = unsafe { core::slice::from_raw_parts_mut(ct, 8) };

    let mut x = u32::from_le_bytes([pt_slice[4], pt_slice[5], pt_slice[6], pt_slice[7]]);
    let mut y = u32::from_le_bytes([pt_slice[0], pt_slice[1], pt_slice[2], pt_slice[3]]);

    for i in 0..SIMON64_128_ROUNDS {
        let tmp = simon_f(x) ^ y ^ ctx_ref.round_keys[i];
        y = x;
        x = tmp;
    }

    let x_bytes = x.to_le_bytes();
    let y_bytes = y.to_le_bytes();

    ct_slice[0..4].copy_from_slice(&y_bytes);
    ct_slice[4..8].copy_from_slice(&x_bytes);

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rs_simon64_128_decrypt_block(
    ctx: *const LwcSimon64128Key,
    ct: *const u8,
    pt: *mut u8,
) -> i32 {
    if ctx.is_null() || ct.is_null() || pt.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let ctx_ref = unsafe { &*ctx };
    let ct_slice = unsafe { core::slice::from_raw_parts(ct, 8) };
    let pt_slice = unsafe { core::slice::from_raw_parts_mut(pt, 8) };

    let mut x = u32::from_le_bytes([ct_slice[4], ct_slice[5], ct_slice[6], ct_slice[7]]);
    let mut y = u32::from_le_bytes([ct_slice[0], ct_slice[1], ct_slice[2], ct_slice[3]]);

    for i in (0..SIMON64_128_ROUNDS).rev() {
        let tmp = simon_f(y) ^ x ^ ctx_ref.round_keys[i];
        x = y;
        y = tmp;
    }

    let x_bytes = x.to_le_bytes();
    let y_bytes = y.to_le_bytes();

    pt_slice[0..4].copy_from_slice(&y_bytes);
    pt_slice[4..8].copy_from_slice(&x_bytes);

    LWC_SUCCESS
}
