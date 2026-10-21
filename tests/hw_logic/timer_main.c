/**
 * @file timer_main.c
 * @brief Unit test of the Pico 2 timer code (timing.c of harness/rp2350_arm and harness/rp2350_rv)
 *        under QEMU -- env=qemu
 *
 * Linked with the QEMU start-up/semihosting of harness/arm or harness/riscv instead of the RP2350
 * start-up (QEMU has no RP2350 machine). It checks the LOGIC only: the DWT probe and SysTick
 * fallback (Arm), mcycle enable (RISC-V), monotonic reads, the mask, the unit name. Under QEMU
 * these counters are not cycle counts; no number printed here is a measurement.
 */

#include "io.h"
#include "platform.h"

int main(void) {
    lwc_printf("RUN,env,qemu\n");
    lwc_printf("UNIT_TEST,hw_timer_logic,%s\n", lwc_platform_name());
    lwc_timer_init();
    lwc_printf("TIMER,%s,%s,%x\n", lwc_timer_source(), lwc_timer_unit(), (unsigned)lwc_timer_mask());
    int fails = 0;
    uint32_t prev = lwc_timer_now(), deltas[3];
    for (int k = 0; k < 3; k++) {
        uint32_t n = 1000u << (2 * k);   /* 1000, 4000, 16000 loop passes */
        deltas[k] = lwc_timer_calibrate(n);
        uint32_t now = lwc_timer_now();
        fails += ((now - prev) & lwc_timer_mask()) == 0;   /* the counter must advance */
        prev = now;
        lwc_printf("CALIB,%u,%u\n", (unsigned)n, (unsigned)deltas[k]);
    }
    /* 4x the work must take more counts than 1x (counts grow with work) */
    fails += !(deltas[1] > deltas[0] && deltas[2] > deltas[1]);
    fails += lwc_timer_unit()[0] != 'c';   /* "cpu_cycles" */
    lwc_printf("UNIT_TEST_RESULT,%s\n", fails ? "fail" : "pass");
    return fails ? 1 : 0;
}
