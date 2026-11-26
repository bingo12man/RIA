#pragma once

#include <stdint.h>
#include <stddef.h>
#include <string.h>

// Standard 44-byte PCM WAV header.
// Audio samples remain unchanged.
static inline void ria_make_wav_header(
    uint8_t header[44],
    uint32_t pcm_size,
    uint32_t sample_rate = 48000
) {
    memset(header, 0, 44);

    const uint16_t channels = 1;
    const uint16_t bits_per_sample = 16;
    const uint32_t byte_rate =
        sample_rate * channels * bits_per_sample / 8;
    const uint16_t block_align =
        channels * bits_per_sample / 8;

    const uint32_t riff_size = pcm_size + 36;

    memcpy(header + 0, "RIFF", 4);
    memcpy(header + 4, &riff_size, 4);
    memcpy(header + 8, "WAVE", 4);
    memcpy(header + 12, "fmt ", 4);

    const uint32_t fmt_size = 16;
    const uint16_t audio_format = 1;

    memcpy(header + 16, &fmt_size, 4);
    memcpy(header + 20, &audio_format, 2);
    memcpy(header + 22, &channels, 2);
    memcpy(header + 24, &sample_rate, 4);
    memcpy(header + 28, &byte_rate, 4);
    memcpy(header + 32, &block_align, 2);
    memcpy(header + 34, &bits_per_sample, 2);

    memcpy(header + 36, "data", 4);
    memcpy(header + 40, &pcm_size, 4);
}
