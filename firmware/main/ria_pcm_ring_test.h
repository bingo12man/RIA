#pragma once
// RIA_PCM_RING_TEST_V1
// Single-task preliminary buffer validation.

#include "ria_pcm_ring.h"
#include "esp_log.h"

static bool ria_pcm_ring_self_test()
{
    RiaPcmRing ring = {};

    // Small buffer deliberately forces wraparound.
    if (!ria_pcm_ring_init(&ring, 16)) {
        ESP_LOGE("RIA_RING_TEST", "Allocation FAIL");
        return false;
    }

    bool ok = true;

    uint8_t input[24];
    uint8_t output[24] = {};

    for (size_t i = 0; i < sizeof(input); ++i)
        input[i] = (uint8_t)i;

    // First transfer: 12 bytes.
    if (ria_pcm_ring_write(
            &ring, input, 12, 0) != 12)
        ok = false;

    if (ria_pcm_ring_read(
            &ring, output, 8, 0) != 8)
        ok = false;

    // Write another 12 bytes, wrapping the buffer.
    if (ria_pcm_ring_write(
            &ring, input + 12, 12, 0) != 12)
        ok = false;

    // Remaining data should be bytes 8 through 23.
    if (ria_pcm_ring_read(
            &ring, output + 8, 16, 0) != 16)
        ok = false;

    for (size_t i = 0; i < 8; ++i) {
        if (output[i] != input[i])
            ok = false;
    }

    for (size_t i = 8; i < 24; ++i) {
        if (output[i] != input[i])
            ok = false;
    }

    // Odd-length transfers must fail.
    if (ria_pcm_ring_write(
            &ring, input, 3, 0) != 0)
        ok = false;

    if (ria_pcm_ring_read(
            &ring, output, 3, 0) != 0)
        ok = false;

    ria_pcm_ring_close(&ring);

    // Closed and empty ring should return immediately.
    if (ria_pcm_ring_read(
            &ring, output, 2, 0) != 0)
        ok = false;

    ria_pcm_ring_destroy(&ring);

    ESP_LOGI(
        "RIA_RING_TEST",
        "PCM ring basic test: %s",
        ok ? "PASS" : "FAIL"
    );

    return ok;
}
