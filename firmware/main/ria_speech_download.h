#pragma once

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "cJSON.h"

#include "private/device_config.h"

// Download speaker-ready WAV from the authenticated Mac bridge.
// Caller owns the returned PSRAM buffer.
static uint8_t *ria_download_speech(
    const char *text,
    size_t *out_size
) {
    if (!out_size)
        return nullptr;

    *out_size = 0;

    if (!text || !text[0] || strlen(text) > 500)
        return nullptr;

    cJSON *payload = cJSON_CreateObject();
    if (!payload)
        return nullptr;

    cJSON_AddStringToObject(payload, "text", text);
    char *body = cJSON_PrintUnformatted(payload);
    cJSON_Delete(payload);

    if (!body)
        return nullptr;

    esp_http_client_config_t config = {};
    config.url = "http://192.168.0.104:8041/speak";
    config.timeout_ms = 100000;
    config.buffer_size = 8192;
    config.buffer_size_tx = 1024;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (!client) {
        cJSON_free(body);
        return nullptr;
    }

    esp_http_client_set_method(
        client, HTTP_METHOD_POST
    );
    esp_http_client_set_header(
        client, "Content-Type", "application/json"
    );
    esp_http_client_set_header(
        client, "X-RIA-Token", RIA_DEVICE_TOKEN
    );

    int body_size = (int)strlen(body);

    esp_err_t err = esp_http_client_open(
        client, body_size
    );

    if (err != ESP_OK) {
        ESP_LOGE("RIA_SPEECH", "Connection failed");
        esp_http_client_cleanup(client);
        cJSON_free(body);
        return nullptr;
    }

    size_t sent = 0;

    while (sent < (size_t)body_size) {
        int n = esp_http_client_write(
            client,
            body + sent,
            body_size - sent
        );

        if (n <= 0) {
            ESP_LOGE("RIA_SPEECH", "Request write failed");
            esp_http_client_close(client);
            esp_http_client_cleanup(client);
            cJSON_free(body);
            return nullptr;
        }

        sent += n;
    }

    cJSON_free(body);

    int64_t headers_start_us = esp_timer_get_time();

    esp_http_client_fetch_headers(client);

    ESP_LOGI(
        "RIA_TIMING",
        "TTS response headers: %lld ms",
        (long long)((esp_timer_get_time() - headers_start_us) / 1000)
    );

    int status =
        esp_http_client_get_status_code(client);

    int64_t content_length =
        esp_http_client_get_content_length(client);

    ESP_LOGI(
        "RIA_SPEECH",
        "HTTP status=%d, content_length=%lld",
        status, (long long)content_length
    );

    if (status != 200 ||
        content_length < 44 ||
        content_length > 4 * 1024 * 1024) {

        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return nullptr;
    }

    // RIA_WAV_4MB_LIMIT_V1
    ESP_LOGI(
        "RIA_SPEECH",
        "Requested WAV=%lld, PSRAM free=%u, largest=%u",
        (long long)content_length,
        (unsigned)heap_caps_get_free_size(
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_largest_free_block(
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
    );

    uint8_t *wav = (uint8_t *)heap_caps_malloc(
        (size_t)content_length,
        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
    );

    if (!wav) {
        ESP_LOGE("RIA_SPEECH", "PSRAM allocation failed");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return nullptr;
    }

    int64_t download_start_us = esp_timer_get_time();

    size_t received = 0;

    while (received < (size_t)content_length) {
        int n = esp_http_client_read(
            client,
            (char *)wav + received,
            (int)((size_t)content_length - received)
        );

        if (n <= 0) {
            break;
        }

        received += n;
    }

    ESP_LOGI(
        "RIA_TIMING",
        "WAV body download: %lld ms (%u bytes)",
        (long long)((esp_timer_get_time() - download_start_us) / 1000),
        (unsigned)received
    );

    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    if (received != (size_t)content_length) {
        ESP_LOGE("RIA_SPEECH", "Incomplete WAV download");
        heap_caps_free(wav);
        return nullptr;
    }

    if (memcmp(wav, "RIFF", 4) != 0 ||
        memcmp(wav + 8, "WAVE", 4) != 0 ||
        memcmp(wav + 12, "fmt ", 4) != 0 ||
        memcmp(wav + 36, "data", 4) != 0) {

        ESP_LOGE("RIA_SPEECH", "Invalid WAV header");
        heap_caps_free(wav);
        return nullptr;
    }

    uint16_t channels = 0;
    uint16_t bits = 0;
    uint32_t rate = 0;

    memcpy(&channels, wav + 22, 2);
    memcpy(&rate, wav + 24, 4);
    memcpy(&bits, wav + 34, 2);

    uint16_t format = 0;
    uint16_t block_align = 0;
    uint32_t byte_rate = 0;
    uint32_t fmt_size = 0;
    uint32_t riff_size = 0;

    memcpy(&riff_size, wav + 4, 4);
    memcpy(&fmt_size, wav + 16, 4);
    memcpy(&format, wav + 20, 2);
    memcpy(&byte_rate, wav + 28, 4);
    memcpy(&block_align, wav + 32, 2);

    if (format != 1 ||
        channels != 1 ||
        rate != 48000 ||
        bits != 16 ||
        fmt_size != 16 ||
        block_align != 2 ||
        byte_rate != 96000 ||
        riff_size != received - 8) {

        ESP_LOGE(
            "RIA_SPEECH",
            "Unsupported or malformed WAV format"
        );

        heap_caps_free(wav);
        return nullptr;
    }

    uint32_t pcm_size = 0;
    memcpy(&pcm_size, wav + 40, 4);

    if (pcm_size == 0 ||
        pcm_size > received - 44 ||
        (pcm_size % 2) != 0) {

        ESP_LOGE("RIA_SPEECH", "Invalid PCM size");
        heap_caps_free(wav);
        return nullptr;
    }

    ESP_LOGI(
        "RIA_SPEECH",
        "WAV verified: 48000 Hz, 16-bit mono, %u PCM bytes",
        (unsigned)pcm_size
    );

    *out_size = pcm_size;

    return wav;
}
