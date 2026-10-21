/* Linker script: RP2350 Cortex-M33 (Raspberry Pi Pico 2), image loaded into SRAM
 *
 * SRAM: 0x20000000-0x20082000, 520 KiB (RP2350 datasheet 2.2.3 / 4.2; Pico SDK addressmap.h
 * SRAM_BASE / SRAM_END). A UF2 "RAM only image" may target exactly this range (datasheet 5.5.2).
 * Split here into a 384 KiB code+rodata region and a 136 KiB data region (including the two
 * 4 KiB banks SRAM8/9 at 0x20080000). Nothing runs from flash, so there is no XIP cache in
 * the measurement path.
 *
 * Boot: the bootrom needs an IMAGE_DEF block anywhere in a RAM image (datasheet 5.9.5); the
 * one in startup.c has a VECTOR_TABLE item pointing at lwc_vectors (0x20000000), from which
 * the bootrom takes the initial SP and PC (datasheet 5.9.3.3, 5.9.5.1).
 */

ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x20000000, LENGTH = 384K   /* SRAM0-5 range: code, rodata, .data load copy */
    RAM   (rwx) : ORIGIN = 0x20060000, LENGTH = 136K   /* to SRAM_END: .data, .bss, stack */
}

__stack_size = 0x8000; /* 32 KiB, as in the QEMU images */

INCLUDE sections.ld
