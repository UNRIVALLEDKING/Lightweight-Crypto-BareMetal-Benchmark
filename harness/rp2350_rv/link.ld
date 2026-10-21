/* Linker script: RP2350 Hazard3 RISC-V (Raspberry Pi Pico 2), image loaded into SRAM
 *
 * SRAM: 0x20000000-0x20082000, 520 KiB (RP2350 datasheet 2.2.3 / 4.2; Pico SDK addressmap.h).
 * Same split as harness/rp2350_arm/link.ld. The bootrom enters a RISC-V image at the
 * ENTRY_POINT item of its IMAGE_DEF (startup.S), else at its lowest address (datasheet
 * 5.9.3.4, 5.9.5.2); _start is both.
 */

ENTRY(_start)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x20000000, LENGTH = 384K
    RAM   (rwx) : ORIGIN = 0x20060000, LENGTH = 136K
}

__stack_size = 0x8000; /* 32 KiB, as in the QEMU images */

INCLUDE sections.ld
