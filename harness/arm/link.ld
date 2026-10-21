/* Linker script: Arm Cortex-M33, QEMU mps2-an505 (works with GNU ld and ld.lld)
 *
 * The CPU resets in Secure state with VTOR = 0x10000000, so code goes in the Secure
 * alias of SSRAM1 and data in the Secure alias of SSRAM2. .data is copied from
 * FLASH at start-up exactly as it would be on a part with real flash.
 */

ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x10000000, LENGTH = 4M   /* SSRAM1, Secure alias */
    RAM   (rwx) : ORIGIN = 0x38000000, LENGTH = 2M   /* SSRAM2, Secure alias */
}

__stack_size = 0x8000; /* 32 KiB */

INCLUDE common.ld
