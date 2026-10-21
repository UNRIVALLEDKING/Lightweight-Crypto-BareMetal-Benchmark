/**
 * @file stats.c
 * @brief Integer-only sample statistics
 */

#include "stats.h"

void lwc_sort_u32(uint32_t *v, size_t n) {
    /* Shell sort (Ciura gaps): small, iterative, no recursion depth to worry about. */
    static const size_t gaps[] = {701, 301, 132, 57, 23, 10, 4, 1};
    for (size_t g = 0; g < sizeof(gaps) / sizeof(gaps[0]); g++) {
        size_t gap = gaps[g];
        for (size_t i = gap; i < n; i++) {
            uint32_t t = v[i];
            size_t j = i;
            while (j >= gap && v[j - gap] > t) {
                v[j] = v[j - gap];
                j -= gap;
            }
            v[j] = t;
        }
    }
}

uint32_t lwc_median_u32(uint32_t *v, size_t n) {
    if (n == 0) {
        return 0;
    }
    lwc_sort_u32(v, n);
    return v[n / 2];
}

uint64_t lwc_udiv64_32(uint64_t num, uint32_t den) {
    uint64_t q = 0, r = 0;
    for (int i = 63; i >= 0; i--) {
        r = (r << 1) | ((num >> i) & 1u);
        if (r >= den) {
            r -= den;
            q |= 1ull << i;
        }
    }
    return q;
}

void lwc_compute_stats(uint32_t *v, size_t n, lwc_stats_t *out) {
    lwc_sort_u32(v, n);
    uint64_t sum = 0;
    for (size_t i = 0; i < n; i++) {
        sum += v[i];
    }
    out->n = (uint32_t)n;
    out->min = v[0];
    out->max = v[n - 1];
    out->median = v[n / 2];
    out->p5 = v[(n * 5) / 100];
    out->p95 = v[(n * 95) / 100];
    out->mean_x100 = (uint32_t)lwc_udiv64_32(sum * 100u, (uint32_t)n);
    out->outliers = 0;
    for (size_t i = 0; i < n; i++) {
        if ((uint64_t)v[i] > 4ull * out->median) {
            out->outliers++;
        }
    }
}
