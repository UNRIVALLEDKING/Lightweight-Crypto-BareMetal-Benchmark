//! Root of the lwc_zig library: exports the C ABI of ciphers/include/lwc_api.h (prefix lwc_zig_).

// Inlining policy (same in all four languages): hints only; plain `fn`, no `inline fn`.
// See docs/METHODOLOGY.md section 4.
pub const simon = @import("simon.zig");
pub const present = @import("present.zig");
pub const ascon = @import("ascon.zig");

/// Safety checks (ReleaseSafe) trap without formatting a message (@trap: UDF on Arm,
/// an illegal instruction on RISC-V); the harness fault handler reports the trap and
/// ends the run with a failure status.
pub const panic = @import("std").debug.no_panic;

// Force the compiler to analyse (and export) every submodule.
comptime {
    _ = simon;
    _ = present;
    _ = ascon;
}
