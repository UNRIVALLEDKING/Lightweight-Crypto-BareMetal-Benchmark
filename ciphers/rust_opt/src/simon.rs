//! SIMON 64/128 Block Cipher Implementation in Rust (hardware-optimized)

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
pub unsafe extern "C" fn lwc_rso_simon64_128_init(
    ctx: *mut LwcSimon64128Key,
    key: *const u8,
) -> i32 {
    if ctx.is_null() || key.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let k_ptr = key as *const u32;
    let rk = unsafe { &mut (*ctx).round_keys };

    rk[0] = u32::from_le(unsafe { core::ptr::read_unaligned(k_ptr) });
    rk[1] = u32::from_le(unsafe { core::ptr::read_unaligned(k_ptr.add(1)) });
    rk[2] = u32::from_le(unsafe { core::ptr::read_unaligned(k_ptr.add(2)) });
    rk[3] = u32::from_le(unsafe { core::ptr::read_unaligned(k_ptr.add(3)) });

    for i in 4..SIMON64_128_ROUNDS {
        let mut tmp = rk[i - 1].rotate_right(3);
        tmp ^= rk[i - 3];
        tmp ^= tmp.rotate_right(1);
        let z = unsafe { *Z3.get_unchecked((i - 4) % 62) } as u32;
        rk[i] = !rk[i - 4] ^ tmp ^ z ^ 3;
    }

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rso_simon64_128_encrypt_block(
    ctx: *const LwcSimon64128Key,
    pt: *const u8,
    ct: *mut u8,
) -> i32 {
    if ctx.is_null() || pt.is_null() || ct.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let rk = unsafe { &(*ctx).round_keys };
    let pt_u32 = pt as *const u32;
    let ct_u32 = ct as *mut u32;

    let mut y = u32::from_le(unsafe { core::ptr::read_unaligned(pt_u32) });
    let mut x = u32::from_le(unsafe { core::ptr::read_unaligned(pt_u32.add(1)) });

    for i in 0..SIMON64_128_ROUNDS {
        let tmp = simon_f(x) ^ y ^ unsafe { *rk.get_unchecked(i) };
        y = x;
        x = tmp;
    }

    unsafe {
        core::ptr::write_unaligned(ct_u32, y.to_le());
        core::ptr::write_unaligned(ct_u32.add(1), x.to_le());
    }

    LWC_SUCCESS
}

#[no_mangle]
pub unsafe extern "C" fn lwc_rso_simon64_128_decrypt_block(
    ctx: *const LwcSimon64128Key,
    ct: *const u8,
    pt: *mut u8,
) -> i32 {
    if ctx.is_null() || ct.is_null() || pt.is_null() {
        return LWC_ERR_NULL_PTR;
    }

    let rk = unsafe { &(*ctx).round_keys };
    let ct_u32 = ct as *const u32;
    let pt_u32 = pt as *mut u32;

    let mut y = u32::from_le(unsafe { core::ptr::read_unaligned(ct_u32) });
    let mut x = u32::from_le(unsafe { core::ptr::read_unaligned(ct_u32.add(1)) });

    for i in (0..SIMON64_128_ROUNDS).rev() {
        let tmp = simon_f(y) ^ x ^ unsafe { *rk.get_unchecked(i) };
        x = y;
        y = tmp;
    }

    unsafe {
        core::ptr::write_unaligned(pt_u32, y.to_le());
        core::ptr::write_unaligned(pt_u32.add(1), x.to_le());
    }

    LWC_SUCCESS
}
