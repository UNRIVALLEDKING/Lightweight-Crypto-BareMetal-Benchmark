/**
 * @file platform.c
 * @brief RISC-V RV32 console, exit and trap reporting via RISC-V semihosting
 *
 * QEMU implements semihosting with -semihosting-config enable=on,target=native;
 * on hardware a debug probe does.
 */

#include "platform.h"
#include "io.h"

#define SYS_WRITE0                  0x04
#define SYS_EXIT                    0x18
#define ADP_STOPPED_APPLICATIONEXIT 0x20026
#define ADP_STOPPED_RUNTIMEERROR    0x20023

uintptr_t lwc_semihost_call(uintptr_t op, uintptr_t arg); /* startup.S */

const char *lwc_platform_name(void) {
    return "rv32imac";
}

void lwc_platform_write(const char *s) {
    lwc_semihost_call(SYS_WRITE0, (uintptr_t)s);
}

void lwc_platform_exit(int code) {
    lwc_semihost_call(SYS_EXIT, code == 0 ? ADP_STOPPED_APPLICATIONEXIT : ADP_STOPPED_RUNTIMEERROR);
    for (;;) {
    }
}

uintptr_t lwc_platform_sp(void) {
    uintptr_t sp;
    __asm__ volatile("mv %0, sp" : "=r"(sp));
    return sp;
}

__attribute__((noreturn)) void lwc_trap_report(uint32_t mcause, uint32_t mepc, uint32_t mtval) {
    lwc_printf("ERROR,fault,mcause=0x%x,mepc=0x%x,mtval=0x%x\n",
               (unsigned)mcause, (unsigned)mepc, (unsigned)mtval);
    lwc_platform_exit(1);
}
