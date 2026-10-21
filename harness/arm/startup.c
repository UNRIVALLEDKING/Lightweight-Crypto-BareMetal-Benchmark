/**
 * @file startup.c
 * @brief Arm Cortex-M33 start-up: vector table, .data/.bss init, fault reporting, semihosting
 *
 * Runs in Secure state (the reset state of mps2-an505), no RTOS, no C library.
 * Console output and exit use Arm semihosting (BKPT 0xAB), which QEMU implements
 * with -semihosting-config enable=on,target=native and a debug probe does on hardware.
 */

#include "platform.h"
#include "io.h"

extern uint32_t __data_load[], __data_start[], __data_end[];
extern uint32_t __bss_start[], __bss_end[];

int main(void);

/* ---- semihosting ------------------------------------------------------- */
#define SYS_WRITE0                  0x04
#define SYS_EXIT                    0x18
#define ADP_STOPPED_APPLICATIONEXIT 0x20026
#define ADP_STOPPED_RUNTIMEERROR    0x20023

static inline uint32_t semihost(uint32_t op, uintptr_t arg) {
    register uint32_t r0 __asm__("r0") = op;
    register uintptr_t r1 __asm__("r1") = arg;
    __asm__ volatile("bkpt 0xAB" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}

const char *lwc_platform_name(void) {
    return "armv8m.main";
}

void lwc_platform_write(const char *s) {
    semihost(SYS_WRITE0, (uintptr_t)s);
}

void lwc_platform_exit(int code) {
    semihost(SYS_EXIT, code == 0 ? ADP_STOPPED_APPLICATIONEXIT : ADP_STOPPED_RUNTIMEERROR);
    for (;;) {
    }
}

uintptr_t lwc_platform_sp(void) {
    uintptr_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    return sp;
}

/* ---- faults ------------------------------------------------------------- */
#define SCB_CFSR  (*(volatile uint32_t *)0xE000ED28u)
#define SCB_HFSR  (*(volatile uint32_t *)0xE000ED2Cu)

/* A Zig safety check (@trap = UDF) or any bad access lands here: report and fail. */
__attribute__((used, noreturn)) static void fault_report(const uint32_t *frame) {
    lwc_printf("ERROR,fault,hfsr=0x%x,cfsr=0x%x,pc=0x%x\n",
               (unsigned)SCB_HFSR, (unsigned)SCB_CFSR, (unsigned)frame[6]);
    lwc_platform_exit(1);
}

/* Naked so that MSP still points at the hardware-stacked frame (r0-r3, r12, lr, pc, xpsr). */
__attribute__((naked)) static void fault_handler(void) {
    __asm__ volatile("mrs r0, msp\n"
                     "b fault_report\n");
}

/* ---- reset -------------------------------------------------------------- */
void Reset_Handler(void) {
    uint32_t *src = __data_load;
    for (uint32_t *dst = __data_start; dst < __data_end; ) {
        *dst++ = *src++;
    }
    for (uint32_t *dst = __bss_start; dst < __bss_end; ) {
        *dst++ = 0;
    }

    lwc_platform_exit(main());
}

__attribute__((section(".vectors"), used))
void (*const lwc_vectors[16])(void) = {
    (void (*)(void))__stack_top,
    Reset_Handler,
    fault_handler, /* NMI */
    fault_handler, /* HardFault */
    fault_handler, /* MemManage */
    fault_handler, /* BusFault */
    fault_handler, /* UsageFault */
    fault_handler, /* SecureFault */
    0, 0, 0,       /* Reserved */
    fault_handler, /* SVCall */
    fault_handler, /* DebugMon */
    0,             /* Reserved */
    fault_handler, /* PendSV */
    fault_handler, /* SysTick (never enabled as an interrupt) */
};
