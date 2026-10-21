/**
 * @file stack.c
 * @brief Stack watermark: the deepest stack use of one call to each operation
 *
 * The free stack below the current stack pointer is painted with a pattern, the
 * operation is called once, and the lowest overwritten word gives its depth in bytes
 * (relative to the caller's stack pointer, so it includes the call itself).
 */

#include "checks.h"
#include "io.h"
#include "platform.h"

#define PAINT 0xA5A5A5A5u

typedef void (*probe_fn)(const lwc_backend_t *b);

/* noinline: the painting loop must run in this frame, with no call below the stack
 * pointer read by lwc_platform_sp() until the probed operation. */
__attribute__((noinline)) static uint32_t stack_depth(probe_fn fn, const lwc_backend_t *b) {
    uintptr_t sp = lwc_platform_sp() & ~(uintptr_t)3;
    volatile uint32_t *p;
    for (p = (volatile uint32_t *)__stack_limit; (uintptr_t)p < sp - 16; p++) {
        *p = PAINT;
    }
    fn(b);
    for (p = (volatile uint32_t *)__stack_limit; (uintptr_t)p < sp && *p == PAINT; p++) {
    }
    return (uint32_t)(sp - (uintptr_t)p);
}

static uint8_t s_key[16], s_nonce[16], s_ad[16], s_in[1024], s_out[1024], s_tag[16];
static lwc_simon64_128_key_t s_sk;
static lwc_present80_key_t s_pk;

__attribute__((noinline)) static void p_empty(const lwc_backend_t *b) { __asm__ volatile("" :: "r"(b) : "memory"); }
static void p_simon_init(const lwc_backend_t *b)   { b->simon_init(&s_sk, s_key); }
static void p_simon_enc(const lwc_backend_t *b)    { b->simon_encrypt(&s_sk, s_in, s_out); }
static void p_simon_dec(const lwc_backend_t *b)    { b->simon_decrypt(&s_sk, s_out, s_in); }
static void p_present_init(const lwc_backend_t *b) { b->present_init(&s_pk, s_key); }
static void p_present_enc(const lwc_backend_t *b)  { b->present_encrypt(&s_pk, s_in, s_out); }
static void p_present_dec(const lwc_backend_t *b)  { b->present_decrypt(&s_pk, s_out, s_in); }
static void p_ascon_enc(const lwc_backend_t *b) {
    b->ascon_encrypt(s_out, s_tag, s_in, sizeof(s_in), s_ad, sizeof(s_ad), s_nonce, s_key);
}
static void p_ascon_dec(const lwc_backend_t *b) {
    b->ascon_decrypt(s_in, s_out, sizeof(s_out), s_tag, s_ad, sizeof(s_ad), s_nonce, s_key);
}

void lwc_run_stack_probes(const lwc_backend_t *b) {
    static const struct { const char *name; probe_fn fn; } probes[] = {
        {"SIMON64_KEYINIT",   p_simon_init},
        {"SIMON64_ENC",       p_simon_enc},
        {"SIMON64_DEC",       p_simon_dec},
        {"PRESENT80_KEYINIT", p_present_init},
        {"PRESENT80_ENC",     p_present_enc},
        {"PRESENT80_DEC",     p_present_dec},
        {"ASCON_AEAD128_ENC", p_ascon_enc},  /* after ENC so DEC sees a valid tag */
        {"ASCON_AEAD128_DEC", p_ascon_dec},
    };
    /* Baseline: the probe call with an empty operation (subtract to get the op alone). */
    lwc_printf("STACK,EMPTY_PROBE,%u\n", (unsigned)stack_depth(p_empty, b));
    for (size_t i = 0; i < sizeof(probes) / sizeof(probes[0]); i++) {
        lwc_printf("STACK,%s,%u\n", probes[i].name, (unsigned)stack_depth(probes[i].fn, b));
    }
}
