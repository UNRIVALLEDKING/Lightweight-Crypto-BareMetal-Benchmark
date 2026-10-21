/**
 * @file timing_rv32.c
 * @brief RISC-V RV32 timing: the mcycle CSR (low 32 bits)
 *
 * mcycle counts core clock cycles on hardware. Under QEMU it is not a cycle count:
 * with -icount it advances with executed instructions, without it it follows host
 * time (see docs/METHODOLOGY.md). The log records the source and QEMU's options.
 * Durations below 2^32 only need the low half, so mcycleh is not read.
 */

#include "platform.h"

void lwc_timer_init(void) {
    /* Make sure the counter is not inhibited (mcountinhibit.CY, priv. spec 1.11+). */
    __asm__ volatile("csrci mcountinhibit, 1");
}

uint32_t lwc_timer_now(void) {
    uint32_t c;
    __asm__ volatile("csrr %0, mcycle" : "=r"(c) :: "memory");
    return c;
}

uint32_t lwc_timer_mask(void) {
    return 0xFFFFFFFFu;
}

const char *lwc_timer_source(void) {
    return "MCYCLE";
}

const char *lwc_timer_unit(void) {
    return "cycles";
}

/* Times `iterations` passes of a 2-instruction loop (addi + bnez): the log's
 * CALIBRATION line, from which the parser derives instructions per tick under QEMU. */
uint32_t lwc_timer_calibrate(uint32_t iterations) {
    uint32_t start = lwc_timer_now();
    __asm__ volatile("1: addi %0, %0, -1\n"
                     "   bnez %0, 1b\n"
                     : "+r"(iterations));
    return (lwc_timer_now() - start) & lwc_timer_mask();
}
