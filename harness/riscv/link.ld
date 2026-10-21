/* Linker script: RISC-V RV32, QEMU virt (works with GNU ld and ld.lld)
 *
 * With -bios none QEMU starts at the ELF entry in DRAM (0x80000000). Code and data
 * are kept in separate regions and .data is copied at start-up, as on a part with flash.
 */

ENTRY(_start)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x80000000, LENGTH = 4M
    RAM   (rwx) : ORIGIN = 0x80400000, LENGTH = 2M
}

__stack_size = 0x8000; /* 32 KiB */

INCLUDE common.ld
