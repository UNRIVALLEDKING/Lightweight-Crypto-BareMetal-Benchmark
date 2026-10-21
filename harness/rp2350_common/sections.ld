/* Section layout of the RP2350 hardware images: harness/common/common.ld plus the
 * bootrom's IMAGE_DEF block (.embedded_block), placed right after the Arm vector table /
 * the RISC-V entry code. common.ld is left unchanged for the QEMU targets.
 *
 * The target script defines MEMORY regions FLASH and RAM (both in SRAM: the image is loaded
 * into SRAM by the bootrom, nothing executes from flash), ENTRY and __stack_size, then
 * INCLUDEs this file. .data keeps a separate load copy, exactly as in the QEMU images, so
 * the start-up code is the same.
 */

SECTIONS
{
    .text :
    {
        KEEP(*(.vectors))
        KEEP(*(.text.init))
        KEEP(*(.embedded_block))
        *(.text .text.*)
        . = ALIGN(4);
    } > FLASH

    .rodata :
    {
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
        . = ALIGN(4);
    } > FLASH

    .data : ALIGN(8)
    {
        __data_start = .;
        *(.data .data.*)
        . = ALIGN(8);
        __global_pointer$ = . + 0x800;
        *(.sdata .sdata.*)
        . = ALIGN(8);
        __data_end = .;
    } > RAM AT > FLASH
    __data_load = LOADADDR(.data);

    .bss (NOLOAD) : ALIGN(8)
    {
        __bss_start = .;
        *(.sbss .sbss.*)
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(8);
        __bss_end = .;
    } > RAM

    .stack (NOLOAD) : ALIGN(16)
    {
        __stack_limit = .;
        . += __stack_size;
        . = ALIGN(16);
        __stack_top = .;
    } > RAM

    /DISCARD/ :
    {
        *(.ARM.exidx*)
        *(.ARM.extab*)
        *(.eh_frame*)
        *(.comment)
        *(.note*)
    }
}
