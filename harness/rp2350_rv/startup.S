/*
 * RP2350 Hazard3 RISC-V start-up (Pico 2, image in SRAM, machine mode, no OS, no C library).
 *
 * Same steps as harness/riscv/startup.S, without semihosting: set sp/gp, mask interrupts,
 * install the trap vector, copy .data, clear .bss, then lwc_hw_start (soc.c: clocks, UART,
 * main, end of run).
 */

    .section .text.init, "ax"
    .globl _start
_start:
    .option push
    .option norelax
    la      gp, __global_pointer$
    .option pop
    la      sp, __stack_top
    csrci   mstatus, 8              /* mstatus.MIE = 0: no interrupt may land in a timed region */
    la      t0, lwc_trap_entry
    csrw    mtvec, t0               /* direct mode (lwc_trap_entry is 4-byte aligned) */

    /* .data: load copy -> RAM */
    la      t0, __data_load
    la      t1, __data_start
    la      t2, __data_end
1:  bgeu    t1, t2, 2f
    lw      t3, 0(t0)
    sw      t3, 0(t1)
    addi    t0, t0, 4
    addi    t1, t1, 4
    j       1b

    /* .bss = 0 */
2:  la      t1, __bss_start
    la      t2, __bss_end
3:  bgeu    t1, t2, 4f
    sw      zero, 0(t1)
    addi    t1, t1, 4
    j       3b

4:  call    lwc_hw_start            /* does not return */
5:  j       5b

/* IMAGE_DEF: RP2350 datasheet 5.9.5.2 (minimum RISC-V IMAGE_DEF, Table 504) plus an
 * ENTRY_POINT item (5.9.3.4, Table 497), as the Pico SDK emits on RISC-V
 * (pico_crt0/embedded_start_block.inc.S, PICO_CRT0_INCLUDE_PICOBIN_ENTRY_POINT_ITEM).
 * Constants from SDK boot/picobin.h. Placed after the entry code by sections.ld. */
    .section .embedded_block, "ax"
    .p2align 2
    .globl lwc_image_def
    .type   lwc_image_def, %object
lwc_image_def:
    .word   0xffffded3              /* PICOBIN_BLOCK_MARKER_START */
    .byte   0x42, 0x01              /* PICOBIN_BLOCK_ITEM_1BS_IMAGE_TYPE, 1 word */
    .hword  0x1101                  /* EXE | CPU_RISCV | CHIP_RP2350 */
    .byte   0x44, 0x03              /* PICOBIN_BLOCK_ITEM_1BS_ENTRY_POINT, 3 words */
    .byte   0, 0
    .word   _start                  /* initial PC */
    .word   __stack_top             /* initial SP */
    .byte   0xff                    /* PICOBIN_BLOCK_ITEM_2BS_LAST */
    .hword  4                       /* size of the items above, in words */
    .byte   0
    .word   0                       /* next block: 0 = loop to itself */
    .word   0xab123579              /* PICOBIN_BLOCK_MARKER_END */
    .size   lwc_image_def, . - lwc_image_def

/* Any exception (illegal instruction from a Zig @trap, misaligned/bad access, ...)
 * ends up here and is reported by lwc_trap_report(mcause, mepc, mtval). */
    .section .text.trap, "ax"
    .balign 4
    .globl lwc_trap_entry
lwc_trap_entry:
    la      sp, __stack_top
    csrr    a0, mcause
    csrr    a1, mepc
    csrr    a2, mtval
    call    lwc_trap_report
6:  j       6b
