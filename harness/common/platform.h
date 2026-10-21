/**
 * @file platform.h
 * @brief What each target directory (harness/arm, harness/riscv) provides to the common code
 */

#ifndef LWC_PLATFORM_H
#define LWC_PLATFORM_H

#include <stdint.h>

/* ---- start-up / I/O (startup + semihosting) ---------------------------- */
const char *lwc_platform_name(void);          /* e.g. "armv8m.main" */
void        lwc_platform_write(const char *s); /* one NUL-terminated string to the host console */
__attribute__((noreturn)) void lwc_platform_exit(int code); /* 0 = success */
uintptr_t   lwc_platform_sp(void);            /* current stack pointer */

/* ---- timing (one file per target) ------------------------------------- */
/* lwc_timer_now() is a free-running up-counter; durations are
 * (end - start) & lwc_timer_mask(). */
void        lwc_timer_init(void);
uint32_t    lwc_timer_now(void);
uint32_t    lwc_timer_mask(void);
const char *lwc_timer_source(void);           /* "DWT_CYCCNT", "SYSTICK", "MCYCLE" */
const char *lwc_timer_unit(void);             /* "cycles" or "systick_ticks" */
uint32_t    lwc_timer_calibrate(uint32_t iterations); /* ticks for iterations x 2 instructions */

/* Linker-script symbols (common.ld) */
extern uint32_t __stack_limit[];
extern uint32_t __stack_top[];

/* Called by the Rust panic handler on the embedded targets (never returns). */
__attribute__((noreturn)) void lwc_panic(uint32_t code);

#endif /* LWC_PLATFORM_H */
