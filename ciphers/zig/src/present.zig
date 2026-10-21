//! PRESENT-80 Lightweight Block Cipher Implementation in Zig

const std = @import("std");

pub const LWC_SUCCESS: i32 = 0;
pub const LWC_ERR_NULL_PTR: i32 = -1;

pub const PRESENT80_ROUNDS: usize = 31;
pub const PRESENT80_ROUND_KEYS: usize = 32;

pub const LwcPresent80Key = extern struct {
    round_keys: [PRESENT80_ROUND_KEYS]u64,
};

const SBOX = [16]u8{
    0xC, 0x5, 0x6, 0xB, 0x9, 0x0, 0xA, 0xD,
    0x3, 0xE, 0xF, 0x8, 0x4, 0x7, 0x1, 0x2,
};

const SBOX_INV = [16]u8{
    0x5, 0xE, 0xF, 0x8, 0xC, 0x1, 0x2, 0xD,
    0xB, 0x4, 0x6, 0x3, 0x0, 0x7, 0x9, 0xA,
};

fn sbox_layer(state: u64) u64 {
    var out: u64 = 0;
    var i: usize = 0;
    while (i < 16) : (i += 1) {
        const nibble: usize = @intCast((state >> @intCast(i * 4)) & 0x0F);
        out |= @as(u64, SBOX[nibble]) << @intCast(i * 4);
    }
    return out;
}

fn sbox_layer_inv(state: u64) u64 {
    var out: u64 = 0;
    var i: usize = 0;
    while (i < 16) : (i += 1) {
        const nibble: usize = @intCast((state >> @intCast(i * 4)) & 0x0F);
        out |= @as(u64, SBOX_INV[nibble]) << @intCast(i * 4);
    }
    return out;
}

fn p_layer(state: u64) u64 {
    var out: u64 = 0;
    var i: usize = 0;
    while (i < 64) : (i += 1) {
        const bit: u64 = (state >> @intCast(i)) & 1;
        const dest: u6 = if (i == 63) 63 else @intCast((i * 16) % 63);
        out |= bit << dest;
    }
    return out;
}

fn p_layer_inv(state: u64) u64 {
    var out: u64 = 0;
    var i: usize = 0;
    while (i < 64) : (i += 1) {
        const bit: u64 = (state >> @intCast(i)) & 1;
        const dest: u6 = if (i == 63) 63 else @intCast((i * 4) % 63);
        out |= bit << dest;
    }
    return out;
}

export fn lwc_zig_present80_init(
    ctx: ?*LwcPresent80Key,
    key: ?[*]const u8,
) callconv(.c) i32 {
    if (ctx == null or key == null) {
        return LWC_ERR_NULL_PTR;
    }

    const c = ctx.?;
    const k = key.?;

    var k_hi: u16 = std.mem.readInt(u16, k[0..2], .big);
    var k_lo: u64 = std.mem.readInt(u64, k[2..10], .big);

    var round: usize = 0;
    while (round < PRESENT80_ROUND_KEYS) : (round += 1) {
        c.round_keys[round] = (@as(u64, k_hi) << 48) | (k_lo >> 16);

        if (round < PRESENT80_ROUNDS) {
            const new_hi: u16 = @intCast((k_lo >> 3) & 0xFFFF);
            var new_lo: u64 = ((k_lo & 7) << 61) | (@as(u64, k_hi) << 45) | (k_lo >> 19);

            const top_nibble: usize = @intCast(new_hi >> 12);
            const updated_hi: u16 = (@as(u16, SBOX[top_nibble]) << 12) | (new_hi & 0x0FFF);

            new_lo ^= @as(u64, @intCast(round + 1)) << 15;

            k_hi = updated_hi;
            k_lo = new_lo;
        }
    }

    return LWC_SUCCESS;
}

export fn lwc_zig_present80_encrypt_block(
    ctx: ?*const LwcPresent80Key,
    pt: ?[*]const u8,
    ct: ?[*]u8,
) callconv(.c) i32 {
    if (ctx == null or pt == null or ct == null) {
        return LWC_ERR_NULL_PTR;
    }

    const c = ctx.?;
    const p = pt.?;
    const out = ct.?;

    var state: u64 = std.mem.readInt(u64, p[0..8], .big);

    var i: usize = 0;
    while (i < PRESENT80_ROUNDS) : (i += 1) {
        state ^= c.round_keys[i];
        state = sbox_layer(state);
        state = p_layer(state);
    }

    state ^= c.round_keys[PRESENT80_ROUNDS];
    std.mem.writeInt(u64, out[0..8], state, .big);

    return LWC_SUCCESS;
}

export fn lwc_zig_present80_decrypt_block(
    ctx: ?*const LwcPresent80Key,
    ct: ?[*]const u8,
    pt: ?[*]u8,
) callconv(.c) i32 {
    if (ctx == null or ct == null or pt == null) {
        return LWC_ERR_NULL_PTR;
    }

    const c = ctx.?;
    const cipher = ct.?;
    const out = pt.?;

    var state: u64 = std.mem.readInt(u64, cipher[0..8], .big);

    var i: usize = PRESENT80_ROUNDS;
    while (i > 0) : (i -= 1) {
        state ^= c.round_keys[i];
        state = p_layer_inv(state);
        state = sbox_layer_inv(state);
    }

    state ^= c.round_keys[0];
    std.mem.writeInt(u64, out[0..8], state, .big);

    return LWC_SUCCESS;
}
