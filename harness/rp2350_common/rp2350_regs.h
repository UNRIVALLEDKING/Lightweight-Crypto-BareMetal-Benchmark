/**
 * @file rp2350_regs.h
 * @brief The RP2350 registers the hardware harness touches, each with its source
 *
 * Sources (no value here is guessed):
 *   [DS]  RP2350 Datasheet, build 80d627281ed5 (build date 01/10/2026),
 *         https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
 *   [SDK] Raspberry Pi Pico SDK, commit 079c6f39023649b154152db30f1d781e884879bc,
 *         src/rp2350/hardware_regs/include/hardware/regs/<file>.h (generated from the same
 *         register description as the datasheet tables)
 *
 * Only plain read / write / read-modify-write accesses are used (one core, no interrupts),
 * so the atomic SET/CLR/XOR aliases of DS 2.1.3 are not needed.
 */

#ifndef LWC_RP2350_REGS_H
#define LWC_RP2350_REGS_H

#include <stdint.h>

#define LWC_REG(addr) (*(volatile uint32_t *)(uintptr_t)(addr))

/* ---- Address map: DS 2.2 / SDK addressmap.h ------------------------------------ */
#define RP_SRAM_BASE       0x20000000u  /* SRAM_BASE */
#define RP_SRAM_END        0x20082000u  /* SRAM_END: 520 KiB = 532,480 B (DS 2.2.3, 4.2) */
#define RP_CLOCKS_BASE     0x40010000u  /* CLOCKS_BASE */
#define RP_RESETS_BASE     0x40020000u  /* RESETS_BASE */
#define RP_IO_BANK0_BASE   0x40028000u  /* IO_BANK0_BASE */
#define RP_PADS_BANK0_BASE 0x40038000u  /* PADS_BANK0_BASE */
#define RP_XOSC_BASE       0x40048000u  /* XOSC_BASE */
#define RP_UART0_BASE      0x40070000u  /* UART0_BASE */
#define RP_WATCHDOG_BASE   0x400d8000u  /* WATCHDOG_BASE */

/* Access: ACCESSCTRL resets UART0/IO_BANK0/PADS_BANK0/RESETS to 0xfc and CLOCKS/XOSC to 0xb8
 * (SDK accessctrl.h *_RESET); both include SP (Secure privileged, bit 3) and CORE0 (bit 4).
 * The harness runs in Arm Secure privileged thread mode / RISC-V M-mode on core 0. The datasheet
 * states that Arm Secure and RISC-V Machine mode accesses are treated alike for the SIO (DS 2.2,
 * "accesses from the Arm Secure state, or RISC-V Machine mode") and for boot RAM (DS 4.3).
 * TODO(verify): DS 10.6 -- that ACCESSCTRL grants RISC-V M-mode the SP (Secure privileged) bit. */

/* ---- XOSC: DS 8.2 / SDK xosc.h --------------------------------------------------- */
#define XOSC_CTRL          LWC_REG(RP_XOSC_BASE + 0x00u)
#define XOSC_STATUS        LWC_REG(RP_XOSC_BASE + 0x04u)
#define XOSC_STARTUP       LWC_REG(RP_XOSC_BASE + 0x0cu)
#define XOSC_CTRL_FREQ_RANGE_1_15MHZ 0xaa0u       /* XOSC_CTRL_FREQ_RANGE_VALUE_1_15MHZ, bits 11:0 */
#define XOSC_CTRL_ENABLE_VALUE       (0xfabu << 12) /* XOSC_CTRL_ENABLE_VALUE_ENABLE << XOSC_CTRL_ENABLE_LSB */
#define XOSC_STATUS_STABLE           (1u << 31)   /* XOSC_STATUS_STABLE_BITS */
/* Crystal frequency: SDK platform_defs.h XOSC_HZ default 12000000; SDK boards/pico2.h does not
 * override it. Startup delay as in SDK hardware_xosc/xosc.c:
 * ((XOSC_HZ / 1000 + 128) / 256) * PICO_XOSC_STARTUP_DELAY_MULTIPLIER (default 6) = 282. */
#define RP_XOSC_HZ        12000000u
#define XOSC_STARTUP_DELAY ((((RP_XOSC_HZ / 1000u) + 128u) / 256u) * 6u)

/* ---- CLOCKS: DS 8.1 / SDK clocks.h ----------------------------------------------- */
#define CLK_REF_CTRL       LWC_REG(RP_CLOCKS_BASE + 0x30u)
#define CLK_REF_DIV        LWC_REG(RP_CLOCKS_BASE + 0x34u)
#define CLK_REF_SELECTED   LWC_REG(RP_CLOCKS_BASE + 0x38u)
#define CLK_SYS_CTRL       LWC_REG(RP_CLOCKS_BASE + 0x3cu)
#define CLK_SYS_DIV        LWC_REG(RP_CLOCKS_BASE + 0x40u)
#define CLK_SYS_SELECTED   LWC_REG(RP_CLOCKS_BASE + 0x44u)
#define CLK_PERI_CTRL      LWC_REG(RP_CLOCKS_BASE + 0x48u)
#define CLK_PERI_DIV       LWC_REG(RP_CLOCKS_BASE + 0x4cu)
#define CLK_SYS_RESUS_CTRL LWC_REG(RP_CLOCKS_BASE + 0x84u)  /* CLOCKS_CLK_SYS_RESUS_CTRL_OFFSET */
#define CLK_REF_CTRL_SRC_BITS   0x3u          /* CLOCKS_CLK_REF_CTRL_SRC_BITS */
#define CLK_REF_CTRL_SRC_ROSC   0x0u          /* CLOCKS_CLK_REF_CTRL_SRC_VALUE_ROSC_CLKSRC_PH */
#define CLK_REF_CTRL_SRC_XOSC   0x2u          /* CLOCKS_CLK_REF_CTRL_SRC_VALUE_XOSC_CLKSRC */
#define CLK_SYS_CTRL_SRC_BITS   0x1u          /* CLOCKS_CLK_SYS_CTRL_SRC_BITS */
#define CLK_SYS_CTRL_SRC_CLKREF 0x0u          /* CLOCKS_CLK_SYS_CTRL_SRC_VALUE_CLK_REF */
#define CLK_PERI_CTRL_ENABLE    (1u << 11)    /* CLOCKS_CLK_PERI_CTRL_ENABLE_BITS */
#define CLK_PERI_CTRL_AUXSRC_BITS   0xe0u     /* CLOCKS_CLK_PERI_CTRL_AUXSRC_BITS; value 0 = clk_sys */
#define CLK_DIV_BY_1            0x00010000u   /* CLK_{REF,SYS,PERI}_DIV reset value: integer divisor 1 */
/* *_SELECTED holds one decoded bit per CTRL.SRC value (DS Table 590). */

/* ---- RESETS: DS 7.5 / SDK resets.h ----------------------------------------------- */
#define RESETS_RESET       LWC_REG(RP_RESETS_BASE + 0x0u)
#define RESETS_RESET_DONE  LWC_REG(RP_RESETS_BASE + 0x8u)
#define RESETS_IO_BANK0    (1u << 6)          /* RESETS_RESET_IO_BANK0_BITS */
#define RESETS_PADS_BANK0  (1u << 9)          /* RESETS_RESET_PADS_BANK0_BITS */
#define RESETS_UART0       (1u << 26)         /* RESETS_RESET_UART0_BITS */

/* ---- GPIO: DS 9.4 (function select), 9.6/9.7 (pads, isolation) / SDK io_bank0.h, pads_bank0.h */
#define IO_GPIO0_CTRL      LWC_REG(RP_IO_BANK0_BASE + 0x04u)
#define IO_GPIO1_CTRL      LWC_REG(RP_IO_BANK0_BASE + 0x0cu)
#define IO_FUNCSEL_UART    0x02u              /* IO_BANK0_GPIO0_CTRL_FUNCSEL_VALUE_UART0_TX, GPIO1: UART0_RX */
#define PADS_GPIO0         LWC_REG(RP_PADS_BANK0_BASE + 0x04u)
#define PADS_GPIO1         LWC_REG(RP_PADS_BANK0_BASE + 0x08u)
#define PADS_ISO           (1u << 8)          /* PADS_BANK0_GPIO0_ISO_BITS: resets to 1, clear after muxing (DS 9.7) */
#define PADS_OD            (1u << 7)          /* PADS_BANK0_GPIO0_OD_BITS: output disable */
#define PADS_IE            (1u << 6)          /* PADS_BANK0_GPIO0_IE_BITS: input enable */
/* Pico 2 default UART pins GP0 = TX, GP1 = RX: SDK boards/pico2.h PICO_DEFAULT_UART_{TX,RX}_PIN */

/* ---- UART0 (Arm PL011): DS 12.1 / SDK uart.h ------------------------------------- */
#define UART_DR            LWC_REG(RP_UART0_BASE + 0x00u)
#define UART_FR            LWC_REG(RP_UART0_BASE + 0x18u)
#define UART_IBRD          LWC_REG(RP_UART0_BASE + 0x24u)
#define UART_FBRD          LWC_REG(RP_UART0_BASE + 0x28u)
#define UART_LCR_H         LWC_REG(RP_UART0_BASE + 0x2cu)
#define UART_CR            LWC_REG(RP_UART0_BASE + 0x30u)
#define UART_FR_TXFF       (1u << 5)          /* UART_UARTFR_TXFF_BITS */
#define UART_FR_BUSY       (1u << 3)          /* UART_UARTFR_BUSY_BITS */
#define UART_LCR_H_WLEN_8  (3u << 5)          /* (8 - 5) << UART_UARTLCR_H_WLEN_LSB */
#define UART_LCR_H_FEN     (1u << 4)          /* UART_UARTLCR_H_FEN_BITS */
#define UART_CR_UARTEN     (1u << 0)
#define UART_CR_TXE        (1u << 8)
#define UART_CR_RXE        (1u << 9)
#define RP_UART_BAUD       115200u            /* 8N1, no flow control */

/* ---- WATCHDOG: DS 12.9 / SDK watchdog.h ------------------------------------------ */
#define WATCHDOG_CTRL      LWC_REG(RP_WATCHDOG_BASE + 0x0u)
#define WATCHDOG_CTRL_ENABLE (1u << 30)       /* WATCHDOG_CTRL_ENABLE_BITS */

#endif /* LWC_RP2350_REGS_H */
