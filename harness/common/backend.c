/**
 * @file backend.c
 * @brief Binds lwc_backend to the prefix given by -DLWC_BACKEND_PREFIX
 */

#include "backend.h"

#if !defined(LWC_BACKEND_PREFIX) || !defined(LWC_BACKEND_LANG)
#error "build with -DLWC_BACKEND_PREFIX=lwc_c|lwc_cpp|lwc_rs|lwc_zig and -DLWC_BACKEND_LANG=\"...\""
#endif

#define LWC_CAT2(a, b) a##b
#define LWC_CAT(a, b)  LWC_CAT2(a, b)
#define FN(name)       LWC_CAT(LWC_BACKEND_PREFIX, name)

const lwc_backend_t lwc_backend = {
    LWC_BACKEND_LANG,
    FN(_simon64_128_init),
    FN(_simon64_128_encrypt_block),
    FN(_simon64_128_decrypt_block),
    FN(_present80_init),
    FN(_present80_encrypt_block),
    FN(_present80_decrypt_block),
    FN(_ascon_aead128_encrypt),
    FN(_ascon_aead128_decrypt),
};
