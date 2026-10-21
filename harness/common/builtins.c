/**
 * @file builtins.c
 * @brief The compiler runtime helpers a backend may call, defined ONCE for every image
 *
 * With size optimisation (-Oz, Rust opt-level "z", Zig ReleaseSmall) the compilers
 * replace 64-bit variable shifts by library calls on 32-bit targets, and Zig on Arm calls
 * the AEABI memory helpers. There is no libgcc / compiler-rt here: this object is linked
 * before every backend library, so all languages (and gcc cells, ahead of libgcc) resolve
 * these helpers to the same code. Rust staticlibs carry their own compiler_builtins; it is
 * only used for helpers not defined here (the symbol gate output and the map show which).
 *
 * Written with 32-bit operations only, so it can never be compiled into a call to itself.
 * Add a helper here only when a link reports it missing.
 */

#include <stddef.h>
#include <stdint.h>

void *memcpy(void *dst, const void *src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);

typedef union {
    uint64_t u;
    struct { uint32_t lo, hi; } w; /* both targets are little-endian */
} dword_t;

static inline uint64_t shl64(uint64_t v, unsigned n) {
    dword_t x = {v};
    if (n >= 32) {
        x.w.hi = x.w.lo << (n - 32);
        x.w.lo = 0;
    } else if (n != 0) {
        x.w.hi = (x.w.hi << n) | (x.w.lo >> (32 - n));
        x.w.lo <<= n;
    }
    return x.u;
}

static inline uint64_t lshr64(uint64_t v, unsigned n) {
    dword_t x = {v};
    if (n >= 32) {
        x.w.lo = x.w.hi >> (n - 32);
        x.w.hi = 0;
    } else if (n != 0) {
        x.w.lo = (x.w.lo >> n) | (x.w.hi << (32 - n));
        x.w.hi >>= n;
    }
    return x.u;
}

static inline int64_t ashr64(int64_t v, unsigned n) {
    dword_t x = {(uint64_t)v};
    int32_t hi = (int32_t)x.w.hi;
    if (n >= 32) {
        x.w.lo = (uint32_t)(hi >> (n - 32));
        x.w.hi = (uint32_t)(hi >> 31);
    } else if (n != 0) {
        x.w.lo = (x.w.lo >> n) | (x.w.hi << (32 - n));
        x.w.hi = (uint32_t)(hi >> n);
    }
    return (int64_t)x.u;
}

/* Generic names (RISC-V, and Arm when not using the AEABI names) */
uint64_t __ashldi3(uint64_t v, int n) { return shl64(v, (unsigned)n); }
uint64_t __lshrdi3(uint64_t v, int n) { return lshr64(v, (unsigned)n); }
int64_t  __ashrdi3(int64_t v, int n)  { return ashr64(v, (unsigned)n); }

#if defined(__ARM_EABI__)
/* Arm run-time ABI (RTABI) names */
uint64_t __aeabi_llsl(uint64_t v, int n) { return shl64(v, (unsigned)n); }
uint64_t __aeabi_llsr(uint64_t v, int n) { return lshr64(v, (unsigned)n); }
int64_t  __aeabi_lasr(int64_t v, int n)  { return ashr64(v, (unsigned)n); }

void __aeabi_memcpy(void *d, const void *s, size_t n)   { memcpy(d, s, n); }
void __aeabi_memcpy4(void *d, const void *s, size_t n)  { memcpy(d, s, n); }
void __aeabi_memcpy8(void *d, const void *s, size_t n)  { memcpy(d, s, n); }
void __aeabi_memmove(void *d, const void *s, size_t n)  { memmove(d, s, n); }
void __aeabi_memmove4(void *d, const void *s, size_t n) { memmove(d, s, n); }
void __aeabi_memmove8(void *d, const void *s, size_t n) { memmove(d, s, n); }
/* Note the AEABI argument order: (dest, n, c) */
void __aeabi_memset(void *d, size_t n, int c)  { memset(d, c, n); }
void __aeabi_memset4(void *d, size_t n, int c) { memset(d, c, n); }
void __aeabi_memset8(void *d, size_t n, int c) { memset(d, c, n); }
void __aeabi_memclr(void *d, size_t n)  { memset(d, 0, n); }
void __aeabi_memclr4(void *d, size_t n) { memset(d, 0, n); }
void __aeabi_memclr8(void *d, size_t n) { memset(d, 0, n); }
#endif
