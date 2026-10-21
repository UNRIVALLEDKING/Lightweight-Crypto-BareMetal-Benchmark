/**
 * @file lwc_cpp_util.hpp
 * @brief Freestanding helpers shared by the C++ backend
 *
 * No standard-library headers: only lwc_api.h (<stdint.h>, <stddef.h>), so the
 * backend builds with -ffreestanding -fno-exceptions -fno-rtti and links without
 * libstdc++ / libc++.
 */

#ifndef LWC_CPP_UTIL_HPP
#define LWC_CPP_UTIL_HPP

#include "lwc_api.h"

namespace lwc::detail {

template <typename T>
constexpr T rotl(T x, unsigned r) {
    return static_cast<T>((x << r) | (x >> (sizeof(T) * 8 - r)));
}

template <typename T>
constexpr T rotr(T x, unsigned r) {
    return static_cast<T>((x >> r) | (x << (sizeof(T) * 8 - r)));
}

inline uint32_t load32_le(const uint8_t *b) {
    return static_cast<uint32_t>(b[0]) |
           (static_cast<uint32_t>(b[1]) << 8) |
           (static_cast<uint32_t>(b[2]) << 16) |
           (static_cast<uint32_t>(b[3]) << 24);
}

inline void store32_le(uint8_t *b, uint32_t v) {
    b[0] = static_cast<uint8_t>(v);
    b[1] = static_cast<uint8_t>(v >> 8);
    b[2] = static_cast<uint8_t>(v >> 16);
    b[3] = static_cast<uint8_t>(v >> 24);
}

inline uint64_t load64_be(const uint8_t *b) {
    return (static_cast<uint64_t>(b[0]) << 56) |
           (static_cast<uint64_t>(b[1]) << 48) |
           (static_cast<uint64_t>(b[2]) << 40) |
           (static_cast<uint64_t>(b[3]) << 32) |
           (static_cast<uint64_t>(b[4]) << 24) |
           (static_cast<uint64_t>(b[5]) << 16) |
           (static_cast<uint64_t>(b[6]) << 8)  |
           (static_cast<uint64_t>(b[7]));
}

inline void store64_be(uint8_t *b, uint64_t v) {
    b[0] = static_cast<uint8_t>(v >> 56);
    b[1] = static_cast<uint8_t>(v >> 48);
    b[2] = static_cast<uint8_t>(v >> 40);
    b[3] = static_cast<uint8_t>(v >> 32);
    b[4] = static_cast<uint8_t>(v >> 24);
    b[5] = static_cast<uint8_t>(v >> 16);
    b[6] = static_cast<uint8_t>(v >> 8);
    b[7] = static_cast<uint8_t>(v);
}

inline uint64_t load64_le(const uint8_t *b) {
    return static_cast<uint64_t>(b[0])         |
           (static_cast<uint64_t>(b[1]) << 8)  |
           (static_cast<uint64_t>(b[2]) << 16) |
           (static_cast<uint64_t>(b[3]) << 24) |
           (static_cast<uint64_t>(b[4]) << 32) |
           (static_cast<uint64_t>(b[5]) << 40) |
           (static_cast<uint64_t>(b[6]) << 48) |
           (static_cast<uint64_t>(b[7]) << 56);
}

inline void store64_le(uint8_t *b, uint64_t v) {
    b[0] = static_cast<uint8_t>(v);
    b[1] = static_cast<uint8_t>(v >> 8);
    b[2] = static_cast<uint8_t>(v >> 16);
    b[3] = static_cast<uint8_t>(v >> 24);
    b[4] = static_cast<uint8_t>(v >> 32);
    b[5] = static_cast<uint8_t>(v >> 40);
    b[6] = static_cast<uint8_t>(v >> 48);
    b[7] = static_cast<uint8_t>(v >> 56);
}

} // namespace lwc::detail

#endif /* LWC_CPP_UTIL_HPP */
