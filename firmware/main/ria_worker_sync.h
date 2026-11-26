#pragma once
// RIA_WORKER_SYNC_V1
// Two-worker completion tracking.
// Both workers must signal completion before caller frees
// shared audio buffers or task context.
//
// The caller must separately ensure each worker has
// finished accessing the context before destroying it.

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

struct RiaWorkerSync {
    SemaphoreHandle_t completed = nullptr;
};

static bool ria_worker_sync_init(RiaWorkerSync *sync)
{
    if (!sync)
        return false;

    sync->completed = xSemaphoreCreateCounting(2, 0);
    return sync->completed != nullptr;
}

static void ria_worker_sync_signal(RiaWorkerSync *sync)
{
    if (sync && sync->completed)
        xSemaphoreGive(sync->completed);
}

static bool ria_worker_sync_wait(
    RiaWorkerSync *sync,
    TickType_t timeout
) {
    if (!sync || !sync->completed)
        return false;

    if (xSemaphoreTake(sync->completed, timeout) != pdTRUE)
        return false;

    return xSemaphoreTake(
        sync->completed,
        timeout
    ) == pdTRUE;
}

static void ria_worker_sync_destroy(RiaWorkerSync *sync)
{
    if (!sync)
        return;

    if (sync->completed)
        vSemaphoreDelete(sync->completed);

    sync->completed = nullptr;
}
