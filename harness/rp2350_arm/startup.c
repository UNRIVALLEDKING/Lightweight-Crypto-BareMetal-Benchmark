/**
 * @file startup.c
 * @brief RP2350 Cortex-M33 start-up (Pico 2, image in SRAM): IMAGE_DEF block, vector table,
 *        .data/.bss init, fault reporting over UART
 *
 * The same structure as harness/arm/startup.c; differences: no semihosting (console and
 * exit are in harness/rp2350_common/soc.c), the bootrom IMAGE_DEF block, explicit VTOR /
 * MSPLIM / PRIMASK set-up because the image is entered from the bootrom, not from reset.
 * Runs in Secure state: the IMAGE_DEF declares a Secure Arm executable.
 */

#include "io.h"
#include "platform.h"

extern uint32_t __data_load[], __data_start[], __data_end[];
extern uint32_t __bss_start[], __bss_end[];
extern void (*const lwc_vectors[16])(void);

__attribute__((noreturn)) void lwc_hw_start(void); /* soc.c */

/* ---- IMAGE_DEF ------------------------------------------------------------------------
 * RP2350 datasheet 5.9.5.1 (minimum Arm IMAGE_DEF, Table 503) plus a VECTOR_TABLE item
 * (5.9.3.3, Table 496), as the Pico SDK emits for no-flash binaries
 * (pico_crt0/embedded_start_block.inc.S, PICO_CRT0_INCLUDE_PICOBIN_VECTOR_TABLE_ITEM).
 * Constants from SDK boot/picobin.h. In a RAM image the bootrom searches all of the
 * downloaded region for the block (datasheet 5.1.5.2), so its position is not critical. */
__asm__(
    "    .section .embedded_block, \"ax\"\n"
    "    .p2align 2\n"
    "    .globl lwc_image_def\n"
    "    .type  lwc_image_def, %object\n"  /* data: disassemblers show it as bytes */
    "lwc_image_def:\n"
    "    .word  0xffffded3\n"              /* PICOBIN_BLOCK_MARKER_START */
    "    .byte  0x42, 0x01\n"              /* PICOBIN_BLOCK_ITEM_1BS_IMAGE_TYPE, 1 word */
    "    .hword 0x1021\n"                  /* EXE | SECURITY_S | CPU_ARM | CHIP_RP2350 */
    "    .byte  0x03, 0x02\n"              /* PICOBIN_BLOCK_ITEM_1BS_VECTOR_TABLE, 2 words */
    "    .hword 0\n"
    "    .word  lwc_vectors\n"
    "    .byte  0xff\n"                    /* PICOBIN_BLOCK_ITEM_2BS_LAST */
    "    .hword 3\n"                       /* size of the items above, in words */
    "    .byte  0\n"
    "    .word  0\n"                       /* next block: 0 = loop to itself */
    "    .word  0xab123579\n"              /* PICOBIN_BLOCK_MARKER_END */
    "    .size  lwc_image_def, . - lwc_image_def\n"
    "    .text\n");

const char *lwc_platform_name(void) {
    return "rp2350.armv8m.main";
}

uintptr_t lwc_platform_sp(void) {
    uintptr_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    return sp;
}

/* ---- faults ------------------------------------------------------------------------- */
#define SCB_VTOR  (*(volatile uint32_t *)0xE000ED08u) /* Armv8-M; SDK m33.h M33_VTOR_OFFSET */
#define SCB_CFSR  (*(volatile uint32_t *)0xE000ED28u)
#define SCB_HFSR  (*(volatile uint32_t *)0xE000ED2Cu)

/* A Zig safety check (@trap = UDF), a stack-limit violation or a bad access lands here. */
__attribute__((used, noreturn)) static void fault_report(const uint32_t *frame) {
    lwc_printf("ERROR,fault,hfsr=0x%x,cfsr=0x%x,pc=0x%x\n",
               (unsigned)SCB_HFSR, (unsigned)SCB_CFSR, (unsigned)frame[6]);
    lwc_printf("LWC_END,fail\n");
    lwc_platform_exit(1);
}

__attribute__((naked)) static void fault_handler(void) {
    __asm__ volatile("mrs r0, msp\n"
                     "b fault_report\n");
}

/* ---- reset -------------------------------------------------------------------------- */
__attribute__((used, noreturn)) static void reset_c(void) {
    uint32_t *src = __data_load;
    for (uint32_t *dst = __data_start; dst < __data_end; ) {
        *dst++ = *src++;
    }
    for (uint32_t *dst = __bss_start; dst < __bss_end; ) {
        *dst++ = 0;
    }
    /* The bootrom found the table through the IMAGE_DEF; make our handlers the live ones. */
    SCB_VTOR = (uint32_t)(uintptr_t)lwc_vectors;
    __asm__ volatile("dsb\n isb" ::: "memory");
    lwc_hw_start();
}

/* Entered from the bootrom with SP from lwc_vectors[0]. Interrupts off (nothing here uses
 * them; no IRQ may land in a timed region), then the stack limit and SP set explicitly:
 * the bootrom's own MSPLIM value is not documented for an image without an ENTRY_POINT
 * item, and an overflow of our 32 KiB stack must fault rather than run into .bss.
 * TODO(verify): datasheet 5.9.3.4 -- what MSPLIM the bootrom leaves (we overwrite it anyway). */
__attribute__((naked, noreturn)) void Reset_Handler(void) {
    __asm__ volatile("cpsid i\n"
                     "ldr r0, =__stack_limit\n"
                     "msr msplim, r0\n"
                     "ldr r0, =__stack_top\n"
                     "mov sp, r0\n"
                     "b reset_c\n"
                     ".ltorg\n");
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
