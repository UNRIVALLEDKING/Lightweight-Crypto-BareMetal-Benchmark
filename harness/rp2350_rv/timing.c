/**
 * @file timing.c
 * @brief RP2350 Hazard3 cycle timer: the mcycle CSR (low 32 bits), unit "cpu_cycles"
 *
 * RP2350 datasheet 3.8 (Hazard3 CSRs): MCYCLE "counts up once per cycle, when
 * mcountinhibit.cy is 0"; MCOUNTINHIBIT.CY resets to 1 ("set by default to save power"),
 * so it is cleared here. Same code as harness/riscv/timing_rv32.c apart from the unit name.
 */

#include "platform.h"

void lwc_timer_init(void) {
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
    return "cpu_cycles";
}

/* Same 2-instruction loop as harness/riscv (addi + bnez); informative on hardware. */
uint32_t lwc_timer_calibrate(uint32_t iterations) {
    uint32_t start = lwc_timer_now();
    __asm__ volatile("1: addi %0, %0, -1\n"
                     "   bnez %0, 1b\n"
                     : "+r"(iterations));
    return (lwc_timer_now() - start) & lwc_timer_mask();
}
