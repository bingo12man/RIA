#pragma once
// RIA_PCM_RING_V3
// Single-producer / single-consumer PCM16 ring.
// Blocking operations use short bounded polling.
// This eliminates missed binary-semaphore wakeups.
// Call destroy only after both workers have exited.

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_heap_caps.h"

struct RiaPcmRing {
    uint8_t *data = nullptr;
    size_t capacity = 0;
    size_t head = 0;
    size_t tail = 0;
    size_t used = 0;
    bool closed = false;
    SemaphoreHandle_t mutex = nullptr;
};

// RIA_RING_WAKEUP_V3
static bool ria_pcm_ring_init(RiaPcmRing *r, size_t cap)
{
    if (!r || cap < 2 || (cap & 1))
        return false;

    r->data = (uint8_t *)heap_caps_malloc(
        cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
    );
    if (!r->data) return false;

    r->mutex = xSemaphoreCreateMutex();
    if (!r->mutex) {
        heap_caps_free(r->data);
        *r = RiaPcmRing{};
        return false;
    }

    r->capacity = cap;
    return true;
}

static void ria_pcm_ring_close(RiaPcmRing *r)
{
    if (!r || !r->mutex) return;
    xSemaphoreTake(r->mutex, portMAX_DELAY);
    r->closed = true;
    xSemaphoreGive(r->mutex);
}

static size_t ria_pcm_ring_write(
    RiaPcmRing *r,
    const uint8_t *src,
    size_t len,
    TickType_t wait_ticks
) {
    if (!r || !r->mutex || !src || (len & 1))
        return 0;

    const TickType_t start = xTaskGetTickCount();
    size_t total = 0;

    while (total < len) {
        xSemaphoreTake(r->mutex, portMAX_DELAY);

        if (r->closed) {
            xSemaphoreGive(r->mutex);
            break;
        }

        size_t count = r->capacity - r->used;
        if (count > len - total) count = len - total;
        count &= ~(size_t)1;

        if (count) {
            size_t first = r->capacity - r->head;
            if (first > count) first = count;

            memcpy(r->data + r->head, src + total, first);
            memcpy(r->data, src + total + first, count - first);

            r->head = (r->head + count) % r->capacity;
            r->used += count;
            total += count;
        }

        xSemaphoreGive(r->mutex);

        if (total == len) break;
        if (wait_ticks == 0) break;

        if (wait_ticks != portMAX_DELAY &&
            (TickType_t)(xTaskGetTickCount() - start)
                >= wait_ticks)
            break;

        vTaskDelay(pdMS_TO_TICKS(10) ?
                   pdMS_TO_TICKS(10) : 1);
    }

    return total;
}

static size_t ria_pcm_ring_read(
    RiaPcmRing *r,
    uint8_t *dst,
    size_t len,
    TickType_t wait_ticks
) {
    if (!r || !r->mutex || !dst || len < 2 || (len & 1))
        return 0;

    const TickType_t start = xTaskGetTickCount();

    while (true) {
        xSemaphoreTake(r->mutex, portMAX_DELAY);

        size_t count = r->used;
        if (count > len) count = len;
        count &= ~(size_t)1;

        if (count) {
            size_t first = r->capacity - r->tail;
            if (first > count) first = count;

            memcpy(dst, r->data + r->tail, first);
            memcpy(dst + first, r->data, count - first);

            r->tail = (r->tail + count) % r->capacity;
            r->used -= count;

            xSemaphoreGive(r->mutex);
            return count;
        }

        bool closed = r->closed;
        xSemaphoreGive(r->mutex);

        if (closed || wait_ticks == 0)
            return 0;

        if (wait_ticks != portMAX_DELAY &&
            (TickType_t)(xTaskGetTickCount() - start)
                >= wait_ticks)
            return 0;

        vTaskDelay(pdMS_TO_TICKS(10) ?
                   pdMS_TO_TICKS(10) : 1);
    }
}

static void ria_pcm_ring_destroy(RiaPcmRing *r)
{
    if (!r) return;
    if (r->mutex) vSemaphoreDelete(r->mutex);
    if (r->data) heap_caps_free(r->data);
    *r = RiaPcmRing{};
}
