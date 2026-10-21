/**
 * @file io.h
 * @brief Minimal formatted output (no C library, no floating point, no 64-bit division)
 *
 * Supported conversions: %s %c %d %u %x %% with optional '-' / '0' flag and width.
 * Arguments are 32-bit (int / unsigned). Output is line-buffered and handed to
 * lwc_platform_write() at every '\n'.
 */

#ifndef LWC_IO_H
#define LWC_IO_H

#include <stdint.h>

__attribute__((format(printf, 1, 2)))
void lwc_printf(const char *fmt, ...);
void lwc_flush(void);

/* Fixed-point helper: prints v/100 as "<int>.<2 digits>" */
void lwc_print_centi(uint32_t v_x100);

#endif /* LWC_IO_H */
