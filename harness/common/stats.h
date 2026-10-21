/**
 * @file stats.h
 * @brief Integer-only sample statistics (no floating point, no 64-bit division helper)
 */

#ifndef LWC_STATS_H
#define LWC_STATS_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t n;
    uint32_t min, p5, median, p95, max;
    uint32_t mean_x100;   /* mean * 100, rounded down */
    uint32_t outliers;    /* samples > 4 x median */
} lwc_stats_t;

/* Sorts `v` in place. */
void     lwc_sort_u32(uint32_t *v, size_t n);
uint32_t lwc_median_u32(uint32_t *v, size_t n);
void     lwc_compute_stats(uint32_t *v, size_t n, lwc_stats_t *out);

/* 64-by-32 unsigned division done in software, so no compiler runtime is needed. */
uint64_t lwc_udiv64_32(uint64_t num, uint32_t den);

#endif /* LWC_STATS_H */
