/* Section layout shared by every target. The target script defines MEMORY regions
 * FLASH and RAM, ENTRY and __stack_size, then INCLUDEs this file.
 *
 * Symbols used by the start-up code and the stack watermark:
 *   __data_load / __data_start / __data_end   .data copy
 *   __bss_start / __bss_end                   .bss clear
 *   __stack_limit / __stack_top               stack region (grows down)
 */

SECTIONS
{
    .text :
    {
        KEEP(*(.vectors))
        KEEP(*(.text.init))
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
