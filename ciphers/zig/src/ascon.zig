//! Ascon-AEAD128 (NIST SP 800-232) implementation in Zig
//!
//! 128-bit key, nonce and tag; 128-bit rate; p[12] for initialisation and
//! finalisation, p[8] for data. Bytes are loaded into 64-bit words little-endian.

const std = @import("std");

pub const LWC_SUCCESS: i32 = 0;
pub const LWC_ERR_NULL_PTR: i32 = -1;
pub const LWC_ERR_AUTH_FAIL: i32 = -2;

const ASCON_AEAD128_IV: u64 = 0x00001000808c0001;
const ASCON_DSEP: u64 = 0x8000000000000000;

/// Round constants; p[n] uses the last n entries.
const RC = [12]u64{
    0xf0, 0xe1, 0xd2, 0xc3, 0xb4, 0xa5, 0x96, 0x87, 0x78, 0x69, 0x5a, 0x4b,
};

fn load64_le(b: []const u8) u64 {
    return std.mem.readInt(u64, b[0..8], .little);
}

fn store64_le(b: []u8, v: u64) void {
    std.mem.writeInt(u64, b[0..8], v, .little);
}

/// b.len < 8
fn load_bytes_le(b: []const u8) u64 {
    var v: u64 = 0;
    for (b, 0..) |byte, i| {
        v |= @as(u64, byte) << @intCast(8 * i);
    }
    return v;
}

fn store_bytes_le(b: []u8, v: u64) void {
    for (b, 0..) |*byte, i| {
        byte.* = @truncate(v >> @intCast(8 * i));
    }
}

/// Padding bit for a partial word of n < 8 bytes.
fn pad(n: usize) u64 {
    return @as(u64, 0x01) << @intCast(8 * n);
}

/// Keep the bytes above the first n (n < 8).
fn clear_bytes(x: u64, n: usize) u64 {
    return x & (~@as(u64, 0) << @intCast(8 * n));
}

fn ascon_permutation(s: *[5]u64, rounds: usize) void {
    var x0 = s[0];
    var x1 = s[1];
    var x2 = s[2];
    var x3 = s[3];
    var x4 = s[4];

    var i: usize = 12 - rounds;
    while (i < 12) : (i += 1) {
        // 1. Round constant
        x2 ^= RC[i];

        // 2. Bit-sliced S-box
        x0 ^= x4; x4 ^= x3; x2 ^= x1;
        const t0 = ~x0 & x1;
        const t1 = ~x1 & x2;
        const t2 = ~x2 & x3;
        const t3 = ~x3 & x4;
        const t4 = ~x4 & x0;
        x0 ^= t1; x1 ^= t2; x2 ^= t3; x3 ^= t4; x4 ^= t0;
        x1 ^= x0; x0 ^= x4; x3 ^= x2; x2 = ~x2;

        // 3. Linear diffusion
        x0 ^= std.math.rotr(u64, x0, 19) ^ std.math.rotr(u64, x0, 28);
        x1 ^= std.math.rotr(u64, x1, 61) ^ std.math.rotr(u64, x1, 39);
        x2 ^= std.math.rotr(u64, x2, 1)  ^ std.math.rotr(u64, x2, 6);
        x3 ^= std.math.rotr(u64, x3, 10) ^ std.math.rotr(u64, x3, 17);
        x4 ^= std.math.rotr(u64, x4, 7)  ^ std.math.rotr(u64, x4, 41);
    }

    s.* = .{ x0, x1, x2, x3, x4 };
}

fn ascon_init(s: *[5]u64, k0: u64, k1: u64, nonce: []const u8) void {
    s.* = .{ ASCON_AEAD128_IV, k0, k1, load64_le(nonce[0..8]), load64_le(nonce[8..16]) };
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

fn ascon_absorb_ad(s: *[5]u64, ad_in: []const u8) void {
    var ad = ad_in;
    if (ad.len > 0) {
        while (ad.len >= 16) {
            s[0] ^= load64_le(ad[0..8]);
            s[1] ^= load64_le(ad[8..16]);
            ascon_permutation(s, 8);
            ad = ad[16..];
        }
        if (ad.len >= 8) {
            s[0] ^= load64_le(ad[0..8]);
            s[1] ^= load_bytes_le(ad[8..]) ^ pad(ad.len - 8);
        } else {
            s[0] ^= load_bytes_le(ad) ^ pad(ad.len);
        }
        ascon_permutation(s, 8);
    }
    s[4] ^= ASCON_DSEP; // Domain separation
}

fn ascon_finalize(s: *[5]u64, k0: u64, k1: u64) void {
    s[2] ^= k0;
    s[3] ^= k1;
    ascon_permutation(s, 12);
    s[3] ^= k0;
    s[4] ^= k1;
}

/// An empty slice (instead of unwrapping a null pointer) when len == 0.
fn in_slice(p: ?[*]const u8, len: usize) []const u8 {
    return if (len == 0) &.{} else p.?[0..len];
}

fn out_slice(p: ?[*]u8, len: usize) []u8 {
    return if (len == 0) &.{} else p.?[0..len];
}

export fn lwc_zig_ascon_aead128_encrypt(
    ct: ?[*]u8,
    tag: ?[*]u8,
    pt: ?[*]const u8,
    pt_len: usize,
    ad: ?[*]const u8,
    ad_len: usize,
    nonce: ?[*]const u8,
    key: ?[*]const u8,
) callconv(.c) i32 {
    if (tag == null or nonce == null or key == null) {
        return LWC_ERR_NULL_PTR;
    }
    if (pt_len > 0 and (pt == null or ct == null)) {
        return LWC_ERR_NULL_PTR;
    }
    if (ad_len > 0 and ad == null) {
        return LWC_ERR_NULL_PTR;
    }

    const k = key.?[0..16];
    const t = tag.?[0..16];
    var p = in_slice(pt, pt_len);
    var c = out_slice(ct, pt_len);

    var s: [5]u64 = undefined;
    const k0 = load64_le(k[0..8]);
    const k1 = load64_le(k[8..16]);

    ascon_init(&s, k0, k1, nonce.?[0..16]);
    ascon_absorb_ad(&s, in_slice(ad, ad_len));

    // Plaintext processing
    while (p.len >= 16) {
        s[0] ^= load64_le(p[0..8]);
        s[1] ^= load64_le(p[8..16]);
        store64_le(c[0..8], s[0]);
        store64_le(c[8..16], s[1]);
        ascon_permutation(&s, 8);
        p = p[16..];
        c = c[16..];
    }
    if (p.len >= 8) {
        const n = p.len - 8;
        s[0] ^= load64_le(p[0..8]);
        store64_le(c[0..8], s[0]);
        s[1] ^= load_bytes_le(p[8..]);
        store_bytes_le(c[8..], s[1]);
        s[1] ^= pad(n);
    } else {
        s[0] ^= load_bytes_le(p);
        store_bytes_le(c, s[0]);
        s[0] ^= pad(p.len);
    }

    ascon_finalize(&s, k0, k1);
    store64_le(t[0..8], s[3]);
    store64_le(t[8..16], s[4]);

    return LWC_SUCCESS;
}

export fn lwc_zig_ascon_aead128_decrypt(
    pt: ?[*]u8,
    ct: ?[*]const u8,
    ct_len: usize,
    tag: ?[*]const u8,
    ad: ?[*]const u8,
    ad_len: usize,
    nonce: ?[*]const u8,
    key: ?[*]const u8,
) callconv(.c) i32 {
    if (tag == null or nonce == null or key == null) {
        return LWC_ERR_NULL_PTR;
    }
    if (ct_len > 0 and (pt == null or ct == null)) {
        return LWC_ERR_NULL_PTR;
    }
    if (ad_len > 0 and ad == null) {
        return LWC_ERR_NULL_PTR;
    }

    const k = key.?[0..16];
    const t = tag.?[0..16];
    var c = in_slice(ct, ct_len);
    var out = out_slice(pt, ct_len);

    var s: [5]u64 = undefined;
    const k0 = load64_le(k[0..8]);
    const k1 = load64_le(k[8..16]);

    ascon_init(&s, k0, k1, nonce.?[0..16]);
    ascon_absorb_ad(&s, in_slice(ad, ad_len));

    // Ciphertext processing
    while (c.len >= 16) {
        const c0 = load64_le(c[0..8]);
        const c1 = load64_le(c[8..16]);
        store64_le(out[0..8], s[0] ^ c0);
        store64_le(out[8..16], s[1] ^ c1);
        s[0] = c0;
        s[1] = c1;
        ascon_permutation(&s, 8);
        c = c[16..];
        out = out[16..];
    }
    if (c.len >= 8) {
        const n = c.len - 8;
        const c0 = load64_le(c[0..8]);
        store64_le(out[0..8], s[0] ^ c0);
        s[0] = c0;
        const c1 = load_bytes_le(c[8..]);
        store_bytes_le(out[8..], s[1] ^ c1);
        s[1] = clear_bytes(s[1], n) | c1;
        s[1] ^= pad(n);
    } else {
        const n = c.len;
        const c0 = load_bytes_le(c);
        store_bytes_le(out, s[0] ^ c0);
        s[0] = clear_bytes(s[0], n) | c0;
        s[0] ^= pad(n);
    }

    ascon_finalize(&s, k0, k1);

    // Constant-time tag check
    const diff = (s[3] ^ load64_le(t[0..8])) | (s[4] ^ load64_le(t[8..16]));

    if (diff != 0) {
        @memset(out_slice(pt, ct_len), 0);
        return LWC_ERR_AUTH_FAIL;
    }

    return LWC_SUCCESS;
}
