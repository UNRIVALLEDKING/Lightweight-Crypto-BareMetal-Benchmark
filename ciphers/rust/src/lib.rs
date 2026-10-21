//! # LWC Rust implementations (runtime-free)
//! `#![no_std]` library exposing the C ABI of `ciphers/include/lwc_api.h` with prefix `lwc_rs_`.

#![no_std]
#![forbid(unsafe_op_in_unsafe_fn)]

// Inlining policy (same in all four languages): hints only (`#[inline]`), nothing forced.
// See docs/METHODOLOGY.md section 4.
pub mod simon;
pub mod present;
pub mod ascon;

pub const LWC_SUCCESS: i32 = 0;
pub const LWC_ERR_NULL_PTR: i32 = -1;
pub const LWC_ERR_AUTH_FAIL: i32 = -2;
pub const LWC_ERR_INVALID_PARAM: i32 = -3;

/// On the embedded targets a panic (bounds check, or an overflow check in the `*-ovf`
/// profiles) is reported by the harness, which then ends the run with a failure status.
#[cfg(all(not(test), target_os = "none"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    extern "C" {
        fn lwc_panic(code: u32) -> !;
    }
    unsafe { lwc_panic(1) }
}

/// Host builds (cdylib for the Python tests): stop on panic.
#[cfg(all(not(test), not(target_os = "none")))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {
        core::hint::spin_loop();
    }
}
