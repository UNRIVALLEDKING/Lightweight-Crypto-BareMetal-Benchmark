/**
 * @file timing_armv8m.c
 * @brief Arm v8-M cycle timing: DWT CYCCNT, with a SysTick fallback
 *
 * DWT CYCCNT counts core clock cycles where it exists and runs. It is optional in
 * v8-M (DWT_CTRL.NOCYCCNT), and an emulator may not model it, so lwc_timer_init()
 * enables it and checks that it advances. If it does not, SysTick is used instead:
 * a 24-bit down-counter on the processor clock (CLKSOURCE = 1), read as an up-count
 * and masked to 24 bits. On QEMU neither source is a cycle count of real silicon
 * (see docs/METHODOLOGY.md); the log records which source was used.
 */

#include "platform.h"

#define DEMCR          (*(volatile uint32_t *)0xE000EDFCu)
#define DEMCR_TRCENA   (1u << 24)
#define DWT_CTRL       (*(volatile uint32_t *)0xE0001000u)
#define DWT_CYCCNT     (*(volatile uint32_t *)0xE0001004u)
#define DWT_CTRL_CYCCNTENA (1u << 0)
#define DWT_CTRL_NOCYCCNT  (1u << 25)

#define SYST_CSR       (*(volatile uint32_t *)0xE000E010u)
#define SYST_RVR       (*(volatile uint32_t *)0xE000E014u)
#define SYST_CVR       (*(volatile uint32_t *)0xE000E018u)
#define SYST_CSR_ENABLE    (1u << 0)
#define SYST_CSR_CLKSOURCE (1u << 2)
#define SYSTICK_MASK   0x00FFFFFFu

static int s_use_dwt;

static int dwt_runs(void) {
    if (DWT_CTRL & DWT_CTRL_NOCYCCNT) {
        return 0;
    }
    DEMCR |= DEMCR_TRCENA;
    DWT_CYCCNT = 0;
    DWT_CTRL |= DWT_CTRL_CYCCNTENA;
    uint32_t a = DWT_CYCCNT;
    for (volatile int i = 0; i < 100; i++) {
    }
    uint32_t b = DWT_CYCCNT;
    return b != a;
}

void lwc_timer_init(void) {
    s_use_dwt = dwt_runs();
    if (!s_use_dwt) {
        SYST_RVR = SYSTICK_MASK;
        SYST_CVR = 0;
        SYST_CSR = SYST_CSR_ENABLE | SYST_CSR_CLKSOURCE; /* no interrupt */
    }
}

uint32_t lwc_timer_now(void) {
    __asm__ volatile("isb" ::: "memory"); /* order the read after earlier instructions */
    if (s_use_dwt) {
        return DWT_CYCCNT;
    }
    return SYSTICK_MASK - (SYST_CVR & SYSTICK_MASK);
}

uint32_t lwc_timer_mask(void) {
    return s_use_dwt ? 0xFFFFFFFFu : SYSTICK_MASK;
}

const char *lwc_timer_source(void) {
    return s_use_dwt ? "DWT_CYCCNT" : "SYSTICK";
}

const char *lwc_timer_unit(void) {
    return s_use_dwt ? "cycles" : "systick_ticks";
}

/* Times `iterations` passes of a 2-instruction loop (subs + bne): the log's
 * CALIBRATION line, from which the parser derives instructions per tick under QEMU. */
uint32_t lwc_timer_calibrate(uint32_t iterations) {
    uint32_t start = lwc_timer_now();
    __asm__ volatile("1: subs %0, %0, #1\n"
                     "   bne 1b\n"
                     : "+r"(iterations) :: "cc");
    return (lwc_timer_now() - start) & lwc_timer_mask();
}
