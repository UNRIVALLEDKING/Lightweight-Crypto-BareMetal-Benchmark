/*
 * RISC-V RV32 start-up (machine mode, no OS, no C library).
 *
 * _start: set sp/gp, install the trap vector, copy .data, clear .bss, call main,
 * exit through semihosting with main's return value.
 */

    .section .text.init, "ax"
    .globl _start
_start:
    .option push
    .option norelax
    la      gp, __global_pointer$
    .option pop
    la      sp, __stack_top
    la      t0, lwc_trap_entry
    csrw    mtvec, t0

    /* .data: FLASH -> RAM */
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

4:  call    main
    call    lwc_platform_exit       /* a0 = main's return value; does not return */
5:  j       5b

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

/* Semihosting trap. The three instructions must be uncompressed and in one page,
 * hence the 16-byte alignment and norvc. a0 = operation, a1 = argument. */
    .section .text.semihost, "ax"
    .balign 16
    .globl lwc_semihost_call
lwc_semihost_call:
    .option push
    .option norvc
    slli    zero, zero, 0x1f
    ebreak
    srai    zero, zero, 7
    .option pop
    ret
