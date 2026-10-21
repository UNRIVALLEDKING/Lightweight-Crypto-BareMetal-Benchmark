/**
 * @file platform.c
 * @brief RP2350 Hazard3: platform name, stack pointer and trap reporting
 *        (console and exit are in harness/rp2350_common/soc.c)
 */

#include "io.h"
#include "platform.h"

const char *lwc_platform_name(void) {
    return "rp2350.rv32.hazard3";
}

uintptr_t lwc_platform_sp(void) {
    uintptr_t sp;
    __asm__ volatile("mv %0, sp" : "=r"(sp));
    return sp;
}

__attribute__((noreturn)) void lwc_trap_report(uint32_t mcause, uint32_t mepc, uint32_t mtval) {
    lwc_printf("ERROR,fault,mcause=0x%x,mepc=0x%x,mtval=0x%x\n",
               (unsigned)mcause, (unsigned)mepc, (unsigned)mtval);
    lwc_printf("LWC_END,fail\n");
    lwc_platform_exit(1);
}
