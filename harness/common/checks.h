/**
 * @file checks.h
 * @brief Correctness checks and measurements that run before any timing
 */

#ifndef LWC_CHECKS_H
#define LWC_CHECKS_H

#include "backend.h"

/* Known-answer tests (vectors generated from vectors/ by scripts/gen_kat_header.py).
 * Prints KAT,<cipher>,<passed>,<total>; returns the number of failures. */
int lwc_run_kats(const lwc_backend_t *b);

/* Deterministic fuzz digest; MUST match host/lwc_host.py:fuzz_digest().
 * Prints FUZZ,...; returns the number of round-trip / auth errors. */
int lwc_run_fuzz(const lwc_backend_t *b);

/* Maximum stack depth of each operation (paint-and-scan watermark). Prints STACK lines. */
void lwc_run_stack_probes(const lwc_backend_t *b);

/* Timed benchmarks. Prints TIMER_OVERHEAD, DATA and SUMMARY lines; returns errors. */
int lwc_run_benchmarks(const lwc_backend_t *b);

#endif /* LWC_CHECKS_H */
