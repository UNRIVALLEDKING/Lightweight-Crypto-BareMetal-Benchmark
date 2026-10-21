/**
 * @file io.c
 * @brief Line-buffered formatted output over the platform console (semihosting)
 */

#include <stdarg.h>
#include <stddef.h>

#include "io.h"
#include "platform.h"

static char s_line[256];
static size_t s_len;

void lwc_flush(void) {
    if (s_len > 0) {
        s_line[s_len] = '\0';
        lwc_platform_write(s_line);
        s_len = 0;
    }
}

static void emit(char c) {
    s_line[s_len++] = c;
    if (c == '\n' || s_len == sizeof(s_line) - 1) {
        lwc_flush();
    }
}

static void emit_u32(uint32_t v, unsigned base, int width, char padc, int left) {
    char buf[12];
    int n = 0;
    do {
        uint32_t d = v % base;
        buf[n++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        v /= base;
    } while (v != 0);
    if (!left) {
        for (int i = n; i < width; i++) emit(padc);
    }
    while (n > 0) emit(buf[--n]);
    if (left) {
        for (int i = n; i < width; i++) emit(' ');
    }
}

void lwc_printf(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    for (; *fmt; fmt++) {
        if (*fmt != '%') {
            emit(*fmt);
            continue;
        }
        fmt++;
        int left = 0, width = 0;
        char padc = ' ';
        if (*fmt == '-') { left = 1; fmt++; }
        if (*fmt == '0') { padc = '0'; fmt++; }
        while (*fmt >= '0' && *fmt <= '9') {
            width = width * 10 + (*fmt++ - '0');
        }
        switch (*fmt) {
        case 's': {
            const char *s = va_arg(ap, const char *);
            int n = 0;
            for (const char *p = s; *p; p++) n++;
            if (!left) for (int i = n; i < width; i++) emit(' ');
            while (*s) emit(*s++);
            if (left) for (int i = n; i < width; i++) emit(' ');
            break;
        }
        case 'c':
            emit((char)va_arg(ap, int));
            break;
        case 'd': {
            int v = va_arg(ap, int);
            if (v < 0) {
                emit('-');
                emit_u32(0u - (uint32_t)v, 10, width, padc, left);
            } else {
                emit_u32((uint32_t)v, 10, width, padc, left);
            }
            break;
        }
        case 'u':
            emit_u32(va_arg(ap, unsigned), 10, width, padc, left);
            break;
        case 'x':
            emit_u32(va_arg(ap, unsigned), 16, width, padc, left);
            break;
        case '%':
            emit('%');
            break;
        default:
            emit('%');
            emit(*fmt);
            break;
        }
    }
    va_end(ap);
}

void lwc_print_centi(uint32_t v_x100) {
    lwc_printf("%u.%02u", (unsigned)(v_x100 / 100), (unsigned)(v_x100 % 100));
}
