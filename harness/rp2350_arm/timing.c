/**
 * @file timing.c
 * @brief RP2350 Cortex-M33 cycle timer: DWT CYCCNT if it counts, else SysTick on the
 *        processor clock. Both count core clock cycles (unit "cpu_cycles").
 *
 * Why a run-time probe: the RP2350 datasheet contradicts itself. Section 3.7.4.11 lists the
 * DWT cycle counter (DWT_CYCCNT.CYCCNT), but the DWT_CTRL register table (Table 149) and the
 * SDK header (m33.h, M33_DWT_CTRL_RESET 0x73741824) give NOCYCCNT = 1 ("does not include a
 * cycle counter"); the same table gives NUMCOMP = 7 where the text says four comparators.
 * harness/arm/timing_armv8m.c trusts NOCYCCNT and would never try the DWT here, so this file
 * ignores the bit, enables the counter and checks that it advances. The DWT_CTRL value
 * read is printed (HWINFO line) so the log records which statement held.
 * TODO(verify): on the board -- datasheet 3.7.4.11 vs Table 149.
 *
 * Registers (Armv8-M, SDK m33.h offsets from PPB 0xE0000000): DEMCR.TRCENA (bit 24) must be
 * set before using the DWT (datasheet 3.7.4.11); DWT_CTRL.CYCCNTENA bit 0; CYCDISS (bit 23,
 * reset 0) would stop CYCCNT in Secure state and is left clear. SysTick CLKSOURCE = 1 selects
 * the processor clock (datasheet Table 195).
 */

#include "io.h"
#include "platform.h"

#define DEMCR          (*(volatile uint32_t *)0xE000EDFCu)
#define DEMCR_TRCENA   (1u << 24)
#define DWT_CTRL       (*(volatile uint32_t *)0xE0001000u)
#define DWT_CYCCNT     (*(volatile uint32_t *)0xE0001004u)
#define DWT_CTRL_CYCCNTENA (1u << 0)
#define DWT_CTRL_NOCYCCNT  (1u << 25)
#define DWT_CTRL_CYCDISS   (1u << 23)

#define SYST_CSR       (*(volatile uint32_t *)0xE000E010u)
#define SYST_RVR       (*(volatile uint32_t *)0xE000E014u)
#define SYST_CVR       (*(volatile uint32_t *)0xE000E018u)
#define SYST_CSR_ENABLE    (1u << 0)
#define SYST_CSR_CLKSOURCE (1u << 2)
#define SYSTICK_MASK   0x00FFFFFFu

static int s_use_dwt;

static int dwt_runs(void) {
    DEMCR |= DEMCR_TRCENA;
    DWT_CTRL &= ~DWT_CTRL_CYCDISS;
    DWT_CYCCNT = 0;
    DWT_CTRL |= DWT_CTRL_CYCCNTENA;
    uint32_t a = DWT_CYCCNT;
    for (volatile int i = 0; i < 100; i++) {
    }
    uint32_t b = DWT_CYCCNT;
    return b != a;
}

void lwc_timer_init(void) {
    uint32_t ctrl = DWT_CTRL;
    s_use_dwt = dwt_runs();
    lwc_printf("HWINFO,dwt_ctrl_at_start,0x%x,nocyccnt_bit,%u,cyccnt_counts,%u\n",
               (unsigned)ctrl, (unsigned)((ctrl & DWT_CTRL_NOCYCCNT) != 0), (unsigned)s_use_dwt);
    if (!s_use_dwt) {
        SYST_RVR = SYSTICK_MASK;
        SYST_CVR = 0;
        SYST_CSR = SYST_CSR_ENABLE | SYST_CSR_CLKSOURCE; /* processor clock, no interrupt */
    }
}

uint32_t lwc_timer_now(void) {
    __asm__ volatile("isb" ::: "memory");
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
    return "cpu_cycles";
}

/* Same 2-instruction loop as harness/arm (subs + bne); on hardware the CALIBRATION line gives
 * the cycles of 2,000,000 loop instructions (informative only, no conversion is applied). */
uint32_t lwc_timer_calibrate(uint32_t iterations) {
    uint32_t start = lwc_timer_now();
    __asm__ volatile("1: subs %0, %0, #1\n"
                     "   bne 1b\n"
                     : "+r"(iterations) :: "cc");
    return (lwc_timer_now() - start) & lwc_timer_mask();
}
