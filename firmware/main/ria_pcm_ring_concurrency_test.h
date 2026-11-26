#pragma once
// RIA_PCM_RING_CONCURRENCY_TEST_V1
// Two-task producer/consumer test. No audio hardware used.

#include "ria_pcm_ring.h"
#include "esp_log.h"
#include "freertos/task.h"

struct RiaRingTestContext {
    RiaPcmRing ring = {};
    SemaphoreHandle_t completed = nullptr;
    volatile bool producer_ok = false;
    volatile bool consumer_ok = false;
};

static uint8_t ria_ring_expected_byte(size_t index)
{
    return (uint8_t)((index * 17u + 29u) & 0xFFu);
}

static void ria_ring_test_producer(void *arg)
{
    auto *ctx = (RiaRingTestContext *)arg;
    uint8_t data[1024];

    bool ok = true;

    for (size_t offset = 0; offset < 262144; offset += sizeof(data)) {
        for (size_t i = 0; i < sizeof(data); ++i)
            data[i] = ria_ring_expected_byte(offset + i);

        size_t n = ria_pcm_ring_write(
            &ctx->ring,
            data,
            sizeof(data),
            pdMS_TO_TICKS(5000)
        );

        if (n != sizeof(data)) {
            ok = false;
            break;
        }
    }

    ctx->producer_ok = ok;
    ria_pcm_ring_close(&ctx->ring);
    xSemaphoreGive(ctx->completed);
    vTaskDelete(nullptr);
}

static void ria_ring_test_consumer(void *arg)
{
    auto *ctx = (RiaRingTestContext *)arg;
    uint8_t data[2048];

    size_t received = 0;
    bool ok = true;

    while (received < 262144) {
        size_t n = ria_pcm_ring_read(
            &ctx->ring,
            data,
            sizeof(data),
            pdMS_TO_TICKS(5000)
        );

        if (n == 0) {
            ok = false;
            break;
        }

        for (size_t i = 0; i < n; ++i) {
            if (data[i] != ria_ring_expected_byte(received + i)) {
                ok = false;
                break;
            }
        }

        if (!ok) break;

        received += n;
    }

    ctx->consumer_ok = ok && received == 262144;
    xSemaphoreGive(ctx->completed);
    vTaskDelete(nullptr);
}

static bool ria_pcm_ring_concurrency_test()
{
    RiaRingTestContext ctx = {};

    if (!ria_pcm_ring_init(&ctx.ring, 4096))
        return false;

    ctx.completed = xSemaphoreCreateCounting(2, 0);

    if (!ctx.completed) {
        ria_pcm_ring_destroy(&ctx.ring);
        return false;
    }

    BaseType_t a = xTaskCreate(
        ria_ring_test_producer,
        "ria_test_prod",
        4096,
        &ctx,
        5,
        nullptr
    );

    BaseType_t b = xTaskCreate(
        ria_ring_test_consumer,
        "ria_test_cons",
        4096,
        &ctx,
        5,
        nullptr
    );

    // If a task cannot start, do not destroy shared
    // resources while another task may be using them.
    if (a != pdPASS || b != pdPASS) {
        ESP_LOGE(
            "RIA_RING_TEST",
            "Task creation failed; reboot required"
        );
        abort();
    }

    bool finished =
        xSemaphoreTake(
            ctx.completed, pdMS_TO_TICKS(15000)
        ) == pdTRUE &&
        xSemaphoreTake(
            ctx.completed, pdMS_TO_TICKS(15000)
        ) == pdTRUE;

    // Prevent use-after-free if a task stalls.
    if (!finished) {
        ESP_LOGE(
            "RIA_RING_TEST",
            "Concurrency timeout; reboot required"
        );
        abort();
    }

    bool passed =
        ctx.producer_ok && ctx.consumer_ok;

    // Both completion signals have been received.
    // Tasks still need time to finish their final
    // scheduler cleanup before shared resources are freed.
    vTaskDelay(pdMS_TO_TICKS(100));

    vSemaphoreDelete(ctx.completed);
    ria_pcm_ring_destroy(&ctx.ring);

    ESP_LOGI(
        "RIA_RING_TEST",
        "Concurrent PCM transfer: %s",
        passed ? "PASS" : "FAIL"
    );

    return passed;
}
