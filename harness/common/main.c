/**
 * @file main.c
 * @brief Benchmark image entry point (one backend per image)
 *
 * Order: build record -> timer calibration -> KATs -> fuzz digest -> stack watermark
 * -> timed benchmarks. A failed KAT stops the run before any timing is printed.
 * The return value becomes the semihosting exit status (0 = every check passed).
 */

#include "build_info.h" /* generated per image by scripts/build_all.py */
#include "checks.h"
#include "io.h"
#include "platform.h"

#define LWC_CALIBRATION_ITERS 1000000u

/* Rust's panic handler calls this on the embedded targets. */
void lwc_panic(uint32_t code) {
    lwc_printf("ERROR,panic,%u\n", (unsigned)code);
    lwc_printf("LWC_END,fail\n");
    lwc_platform_exit(1);
}

int main(void) {
    lwc_timer_init();

    lwc_printf("LWC_BEGIN,2\n");
    for (unsigned i = 0; i < sizeof(lwc_build_info) / sizeof(lwc_build_info[0]); i++) {
        lwc_printf("BUILD,%s,%s\n", lwc_build_info[i][0], lwc_build_info[i][1]);
    }
    lwc_printf("BUILD,backend_lang,%s\n", lwc_backend.lang);
    lwc_printf("BUILD,platform,%s\n", lwc_platform_name());
    lwc_printf("TIMER,%s,%s,%x\n", lwc_timer_source(), lwc_timer_unit(), (unsigned)lwc_timer_mask());
    lwc_printf("CALIBRATION,%u,%u,%u\n", (unsigned)LWC_CALIBRATION_ITERS,
               (unsigned)(2 * LWC_CALIBRATION_ITERS), (unsigned)lwc_timer_calibrate(LWC_CALIBRATION_ITERS));

    int failures = lwc_run_kats(&lwc_backend);
    if (failures) {
        lwc_printf("ERROR,kat,%d\n", failures);
        lwc_printf("LWC_END,fail\n");
        return 1;
    }
    failures += lwc_run_fuzz(&lwc_backend);
    lwc_run_stack_probes(&lwc_backend);
    failures += lwc_run_benchmarks(&lwc_backend);

    lwc_printf("LWC_END,%s\n", failures ? "fail" : "ok");
    return failures ? 1 : 0;
}
