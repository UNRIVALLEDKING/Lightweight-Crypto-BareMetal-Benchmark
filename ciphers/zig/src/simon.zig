//! SIMON 64/128 Block Cipher Implementation in Zig

const std = @import("std");

pub const LWC_SUCCESS: i32 = 0;
pub const LWC_ERR_NULL_PTR: i32 = -1;

pub const SIMON64_128_ROUNDS: usize = 44;

pub const LwcSimon64128Key = extern struct {
    round_keys: [SIMON64_128_ROUNDS]u32,
};

const Z3 = [62]u8{
    1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0,
    0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0, 1, 1, 1, 1,
};

fn simon_f(x: u32) u32 {
    return (std.math.rotl(u32, x, 1) & std.math.rotl(u32, x, 8)) ^ std.math.rotl(u32, x, 2);
}

export fn lwc_zig_simon64_128_init(
    ctx: ?*LwcSimon64128Key,
    key: ?[*]const u8,
) callconv(.c) i32 {
    if (ctx == null or key == null) {
        return LWC_ERR_NULL_PTR;
    }

    const c = ctx.?;
    const k = key.?;

    c.round_keys[0] = std.mem.readInt(u32, k[0..4], .little);
    c.round_keys[1] = std.mem.readInt(u32, k[4..8], .little);
    c.round_keys[2] = std.mem.readInt(u32, k[8..12], .little);
    c.round_keys[3] = std.mem.readInt(u32, k[12..16], .little);

    var i: usize = 4;
    while (i < SIMON64_128_ROUNDS) : (i += 1) {
        var tmp = std.math.rotr(u32, c.round_keys[i - 1], 3);
        tmp ^= c.round_keys[i - 3];
        tmp ^= std.math.rotr(u32, tmp, 1);
        c.round_keys[i] = ~c.round_keys[i - 4] ^ tmp ^ @as(u32, Z3[(i - 4) % 62]) ^ 3;
    }

    return LWC_SUCCESS;
}

export fn lwc_zig_simon64_128_encrypt_block(
    ctx: ?*const LwcSimon64128Key,
    pt: ?[*]const u8,
    ct: ?[*]u8,
) callconv(.c) i32 {
    if (ctx == null or pt == null or ct == null) {
        return LWC_ERR_NULL_PTR;
    }

    const c = ctx.?;
    const p = pt.?;
    const out = ct.?;

    var x = std.mem.readInt(u32, p[4..8], .little);
    var y = std.mem.readInt(u32, p[0..4], .little);

    var i: usize = 0;
    while (i < SIMON64_128_ROUNDS) : (i += 1) {
        const tmp = simon_f(x) ^ y ^ c.round_keys[i];
        y = x;
        x = tmp;
    }

    std.mem.writeInt(u32, out[0..4], y, .little);
    std.mem.writeInt(u32, out[4..8], x, .little);

    return LWC_SUCCESS;
}

export fn lwc_zig_simon64_128_decrypt_block(
    ctx: ?*const LwcSimon64128Key,
    ct: ?[*]const u8,
    pt: ?[*]u8,
) callconv(.c) i32 {
    if (ctx == null or ct == null or pt == null) {
        return LWC_ERR_NULL_PTR;
    }

    const c = ctx.?;
    const cipher = ct.?;
    const out = pt.?;

    var x = std.mem.readInt(u32, cipher[4..8], .little);
    var y = std.mem.readInt(u32, cipher[0..4], .little);

    var i: usize = SIMON64_128_ROUNDS;
    while (i > 0) {
        i -= 1;
        const tmp = simon_f(y) ^ x ^ c.round_keys[i];
        x = y;
        y = tmp;
    }

    std.mem.writeInt(u32, out[0..4], y, .little);
    std.mem.writeInt(u32, out[4..8], x, .little);

    return LWC_SUCCESS;
}
