//! # LWC Rust (hardware-optimized) implementations
//! `#![no_std]` library exposing the C ABI of `ciphers/include/lwc_api.h` with prefix `lwc_rso_`.

#![no_std]

pub mod simon;
pub mod present;
pub mod ascon;

pub const LWC_SUCCESS: i32 = 0;
pub const LWC_ERR_NULL_PTR: i32 = -1;
pub const LWC_ERR_AUTH_FAIL: i32 = -2;
pub const LWC_ERR_INVALID_PARAM: i32 = -3;

#[cfg(all(not(test), target_os = "none"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    extern "C" {
        fn lwc_panic(code: u32) -> !;
    }
    unsafe { lwc_panic(1) }
}

#[cfg(all(not(test), not(target_os = "none")))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {
        core::hint::spin_loop();
    }
}
