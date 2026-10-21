/**
 * @file soc.c
 * @brief RP2350 (Pico 2) board bring-up shared by the Arm and RISC-V hardware images:
 *        clocks, UART0 console on GP0/GP1, end of run
 *
 * Replaces semihosting (which needs a debugger; without one BKPT / EBREAK just faults)
 * behind the same platform.h interface used by harness/common. Register sources are in
 * rp2350_regs.h.
 *
 * Clock plan: clk_ref = XOSC (12 MHz crystal), clk_sys = clk_ref, clk_peri = clk_sys, all
 * dividers 1. No PLL: fewer hardware facts to get right, and the image runs from SRAM, which
 * has no wait states to scale with the clock. The core clock is therefore 12 MHz and printed
 * as RUN,clock_hz. Cycle counts do not depend on it; wall time does (not measured).
 *
 * Nothing here is used by the QEMU targets.
 */

#include "io.h"
#include "platform.h"
#include "rp2350_regs.h"

#define RP_CLOCK_HZ RP_XOSC_HZ /* clk_sys = clk_ref = XOSC */

int main(void);

static void clocks_init(void) {
    /* The bootrom may leave the watchdog running (it reboots through it after a UF2 RAM
     * download, DS 5.2.5). A benchmark run takes far longer than any watchdog period. */
    WATCHDOG_CTRL &= ~WATCHDOG_CTRL_ENABLE;

    /* Same order as SDK pico_runtime_init/runtime_init_clocks.c: resus off, XOSC on
     * (hardware_xosc/xosc.c:xosc_init(); safe if the bootrom already started it), then move
     * clk_sys to clk_ref and clk_ref to the ROSC before selecting the XOSC, so that no clock
     * is ever switched while it drives the core. Both are glitchless muxes; *_SELECTED is
     * one-hot per SRC value (DS Table 590). */
    CLK_SYS_RESUS_CTRL = 0;
    XOSC_CTRL = XOSC_CTRL_FREQ_RANGE_1_15MHZ;
    XOSC_STARTUP = XOSC_STARTUP_DELAY;
    XOSC_CTRL |= XOSC_CTRL_ENABLE_VALUE;
    while (!(XOSC_STATUS & XOSC_STATUS_STABLE)) {
    }
    CLK_SYS_CTRL = (CLK_SYS_CTRL & ~CLK_SYS_CTRL_SRC_BITS) | CLK_SYS_CTRL_SRC_CLKREF;
    while (CLK_SYS_SELECTED != (1u << CLK_SYS_CTRL_SRC_CLKREF)) {
    }
    CLK_REF_CTRL = (CLK_REF_CTRL & ~CLK_REF_CTRL_SRC_BITS) | CLK_REF_CTRL_SRC_ROSC;
    while (CLK_REF_SELECTED != (1u << CLK_REF_CTRL_SRC_ROSC)) {
    }
    CLK_REF_DIV = CLK_DIV_BY_1;
    CLK_SYS_DIV = CLK_DIV_BY_1;
    CLK_REF_CTRL = (CLK_REF_CTRL & ~CLK_REF_CTRL_SRC_BITS) | CLK_REF_CTRL_SRC_XOSC;
    while (CLK_REF_SELECTED != (1u << CLK_REF_CTRL_SRC_XOSC)) {
    }

    /* clk_peri (UART clock) from clk_sys. Its aux mux is not glitchless: disable, wait, select,
     * enable -- the order of SDK hardware_clocks clock_configure(). */
    CLK_PERI_CTRL &= ~CLK_PERI_CTRL_ENABLE;
    for (volatile int i = 0; i < 64; i++) {
    }
    CLK_PERI_CTRL = CLK_PERI_CTRL & ~CLK_PERI_CTRL_AUXSRC_BITS; /* AUXSRC 0 = clk_sys */
    CLK_PERI_DIV = CLK_DIV_BY_1;
    CLK_PERI_CTRL |= CLK_PERI_CTRL_ENABLE;
}

/* PL011 divisor exactly as SDK hardware_uart/uart.c:uart_set_baudrate():
 * div = 8 * clk / baud + 1; IBRD = div >> 7; FBRD = (div & 0x7f) >> 1.
 * 12 MHz, 115200 -> IBRD 6, FBRD 33 -> 115,108 baud (-0.08 %). */
static void uart_init(void) {
    uint32_t sel = RESETS_IO_BANK0 | RESETS_PADS_BANK0 | RESETS_UART0;
    RESETS_RESET |= sel;            /* known state even if the bootrom used them */
    RESETS_RESET &= ~sel;
    while ((RESETS_RESET_DONE & sel) != sel) {
    }

    uint32_t div = 8u * RP_CLOCK_HZ / RP_UART_BAUD + 1u;
    UART_IBRD = div >> 7;
    UART_FBRD = (div & 0x7fu) >> 1;
    UART_LCR_H = UART_LCR_H_WLEN_8 | UART_LCR_H_FEN; /* also latches IBRD/FBRD; 8N1, FIFOs on */
    UART_CR = UART_CR_UARTEN | UART_CR_TXE | UART_CR_RXE;

    /* GP0 = UART0 TX, GP1 = UART0 RX; pads: output enabled, RX input enabled, then release
     * the isolation latch (DS 9.7: clear ISO after the muxing is set up). */
    IO_GPIO0_CTRL = IO_FUNCSEL_UART;
    IO_GPIO1_CTRL = IO_FUNCSEL_UART;
    PADS_GPIO0 = (PADS_GPIO0 & ~PADS_OD) | PADS_IE;
    PADS_GPIO1 = (PADS_GPIO1 & ~PADS_OD) | PADS_IE;
    PADS_GPIO0 &= ~PADS_ISO;
    PADS_GPIO1 &= ~PADS_ISO;
}

static void uart_putc(char c) {
    while (UART_FR & UART_FR_TXFF) {
    }
    UART_DR = (uint32_t)(uint8_t)c;
}

static void uart_drain(void) {
    while (UART_FR & UART_FR_BUSY) {
    }
}

/* ---- platform.h --------------------------------------------------------------------- */
void lwc_platform_write(const char *s) {
    while (*s) {
        uart_putc(*s++);
    }
}

/* There is no host to return to: report, drain the UART, and stop. The host script ends
 * the capture at LWC_END / EXIT. */
void lwc_platform_exit(int code) {
    lwc_flush();
    lwc_printf("EXIT,%d\n", code);
    lwc_flush();
    uart_drain();
    for (;;) {
    }
}

/* Called by the start-up code after .data/.bss are initialised, with interrupts masked. */
__attribute__((noreturn)) void lwc_hw_start(void) {
    clocks_init();
    uart_init();
    lwc_printf("\nRUN,clock_hz,%u\n", (unsigned)RP_CLOCK_HZ);
    lwc_printf("RUN,clock_source,xosc (clk_sys = clk_ref = XOSC, no PLL)\n");
    lwc_platform_exit(main());
}
