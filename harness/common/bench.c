/**
 * @file bench.c
 * @brief Timed benchmarks, shared by every target and backend
 *
 * Each operation is timed individually: counter read, one backend call through the
 * function table, counter read. LWC_BATCHES x LWC_ITERS samples per operation after
 * LWC_WARMUP untimed calls. Inputs change every iteration and buffers pass through
 * compiler barriers, so no work can be hoisted or removed. Every return code is checked.
 *
 * Output: DATA,<op>,<batch>,<batch median>
 *         SUMMARY,<op>,<bytes>,<n>,<min>,<p5>,<median>,<p95>,<max>,<mean>,<outliers>
 * in raw counter units (see TIMER and CALIBRATION lines).
 */

#include "checks.h"
#include "io.h"
#include "platform.h"
#include "stats.h"

#ifndef LWC_WARMUP
#define LWC_WARMUP 20
#endif
#ifndef LWC_BATCHES
#define LWC_BATCHES 10
#endif
#ifndef LWC_ITERS
#define LWC_ITERS 100
#endif
#define LWC_SAMPLES (LWC_BATCHES * LWC_ITERS)

/* Compiler barrier: the buffer at p may be read or written here. */
static inline __attribute__((always_inline)) void BARRIER(const void *p) {
    __asm__ volatile("" : : "r"(p) : "memory");
}

static uint32_t s_samples[LWC_SAMPLES];
static uint32_t s_mask;
static int s_errors;

static void report(const char *op, uint32_t bytes) {
    for (int b = 0; b < LWC_BATCHES; b++) {
        /* median of each batch, sorted in place (the full set is re-sorted below) */
        lwc_printf("DATA,%s,%d,%u\n", op, b, (unsigned)lwc_median_u32(&s_samples[b * LWC_ITERS], LWC_ITERS));
    }
    lwc_stats_t st;
    lwc_compute_stats(s_samples, LWC_SAMPLES, &st);
    lwc_printf("SUMMARY,%s,%u,%u,%u,%u,%u,%u,%u,", op, (unsigned)bytes, (unsigned)st.n,
               (unsigned)st.min, (unsigned)st.p5, (unsigned)st.median, (unsigned)st.p95, (unsigned)st.max);
    lwc_print_centi(st.mean_x100);
    lwc_printf(",%u\n", (unsigned)st.outliers);
    if (st.max > s_mask / 2) {
        lwc_printf("ERROR,counter_range,%s\n", op); /* a sample may have wrapped the counter */
        s_errors++;
    }
}

/* Times `call` (an expression returning int32_t) and checks it returns `expect`. */
#define TIME_OP(op, bytes, vary, call, expect)                                   \
    do {                                                                         \
        for (int w_ = 0; w_ < LWC_WARMUP; w_++) {                                \
            (void)(call);                                                        \
        }                                                                        \
        for (int i_ = 0; i_ < LWC_SAMPLES; i_++) {                               \
            vary;                                                                \
            uint32_t t0_ = lwc_timer_now();                                      \
            int32_t rc_ = (call);                                                \
            uint32_t t1_ = lwc_timer_now();                                      \
            s_samples[i_] = (t1_ - t0_) & s_mask;                                \
            s_errors += rc_ != (expect);                                         \
        }                                                                        \
        report(op, bytes);                                                       \
    } while (0)

static uint8_t s_key[16], s_nonce[16], s_ad[16], s_pt[1024], s_ct[1024], s_out[1024], s_tag[16];

static void timer_overhead(void) {
    for (int i = 0; i < LWC_SAMPLES; i++) {
        uint32_t t0 = lwc_timer_now();
        uint32_t t1 = lwc_timer_now();
        s_samples[i] = (t1 - t0) & s_mask;
    }
    lwc_stats_t st;
    lwc_compute_stats(s_samples, LWC_SAMPLES, &st);
    lwc_printf("TIMER_OVERHEAD,%u,%u\n", (unsigned)st.min, (unsigned)st.median);
}

static void bench_simon(const lwc_backend_t *b) {
    lwc_simon64_128_key_t ctx;
    for (int i = 0; i < 16; i++) s_key[i] = (uint8_t)i;
    for (int i = 0; i < 8; i++) s_pt[i] = (uint8_t)(0x60 + i);

    TIME_OP("SIMON64_KEYINIT", 0, (s_key[0]++, BARRIER(s_key)), b->simon_init(&ctx, s_key), LWC_SUCCESS);
    BARRIER(&ctx);
    TIME_OP("SIMON64_ENC", 8, (s_pt[0]++, BARRIER(s_pt)), b->simon_encrypt(&ctx, s_pt, s_ct), LWC_SUCCESS);
    BARRIER(s_ct);
    TIME_OP("SIMON64_DEC", 8, (s_ct[0]++, BARRIER(s_ct)), b->simon_decrypt(&ctx, s_ct, s_out), LWC_SUCCESS);
    BARRIER(s_out);
}

static void bench_present(const lwc_backend_t *b) {
    lwc_present80_key_t ctx;
    for (int i = 0; i < 10; i++) s_key[i] = (uint8_t)(0x10 * i);
    for (int i = 0; i < 8; i++) s_pt[i] = (uint8_t)(0x70 + i);

    TIME_OP("PRESENT80_KEYINIT", 0, (s_key[0]++, BARRIER(s_key)), b->present_init(&ctx, s_key), LWC_SUCCESS);
    BARRIER(&ctx);
    TIME_OP("PRESENT80_ENC", 8, (s_pt[0]++, BARRIER(s_pt)), b->present_encrypt(&ctx, s_pt, s_ct), LWC_SUCCESS);
    BARRIER(s_ct);
    TIME_OP("PRESENT80_DEC", 8, (s_ct[0]++, BARRIER(s_ct)), b->present_decrypt(&ctx, s_ct, s_out), LWC_SUCCESS);
    BARRIER(s_out);
}

static void bench_ascon_size(const lwc_backend_t *b, const char *enc_op, const char *dec_op, uint32_t n) {
    for (int i = 0; i < 16; i++) {
        s_key[i] = (uint8_t)i;
        s_nonce[i] = (uint8_t)(0x10 + i);
        s_ad[i] = (uint8_t)(0x20 + i);
    }
    for (uint32_t i = 0; i < n; i++) s_pt[i] = (uint8_t)i;

    /* Encryption: a fresh nonce per call. */
    TIME_OP(enc_op, n, (s_nonce[0]++, BARRIER(s_nonce)),
            b->ascon_encrypt(s_ct, s_tag, s_pt, n, s_ad, sizeof(s_ad), s_nonce, s_key), LWC_SUCCESS);
    BARRIER(s_ct);

    /* Decryption: always the valid ciphertext and tag just produced (success path).
     * Inputs are fixed, so the barrier on the output is what keeps every call. */
    TIME_OP(dec_op, n, BARRIER(s_out),
            b->ascon_decrypt(s_out, s_ct, n, s_tag, s_ad, sizeof(s_ad), s_nonce, s_key), LWC_SUCCESS);
    BARRIER(s_out);
}

static void bench_ascon(const lwc_backend_t *b) {
    bench_ascon_size(b, "ASCON_AEAD128_ENC_16B", "ASCON_AEAD128_DEC_16B", 16);
    bench_ascon_size(b, "ASCON_AEAD128_ENC_64B", "ASCON_AEAD128_DEC_64B", 64);
    bench_ascon_size(b, "ASCON_AEAD128_ENC_256B", "ASCON_AEAD128_DEC_256B", 256);
    bench_ascon_size(b, "ASCON_AEAD128_ENC_1024B", "ASCON_AEAD128_DEC_1024B", 1024);
}

int lwc_run_benchmarks(const lwc_backend_t *b) {
    s_mask = lwc_timer_mask();
    s_errors = 0;
    lwc_printf("BENCH_CONFIG,%d,%d,%d\n", LWC_WARMUP, LWC_BATCHES, LWC_ITERS);
    timer_overhead();
    bench_simon(b);
    bench_present(b);
    bench_ascon(b);
    if (s_errors) {
        lwc_printf("ERROR,bench,%d\n", s_errors);
    }
    return s_errors;
}
