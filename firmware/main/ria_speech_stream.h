#pragma once

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_http_client.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "cJSON.h"

#include "esp_es8311_port.h"
#include "private/device_config.h"

// Independent streaming implementation.
// Existing full-WAV playback remains available.
static bool ria_stream_speech(const char *text)
{
    if (!text || !text[0] || strlen(text) > 500)
        return false;

    cJSON *payload = cJSON_CreateObject();
    if (!payload)
        return false;

    cJSON_AddStringToObject(payload, "text", text);
    char *body = cJSON_PrintUnformatted(payload);
    cJSON_Delete(payload);

    if (!body)
        return false;

    esp_http_client_config_t config = {};
    config.url = "http://192.168.0.104:8041/speak";
    config.timeout_ms = 100000;
    config.buffer_size = 8192;
    config.buffer_size_tx = 1024;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (!client) {
        cJSON_free(body);
        return false;
    }

    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(
        client, "Content-Type", "application/json"
    );
    esp_http_client_set_header(
        client, "X-RIA-Token", RIA_DEVICE_TOKEN
    );

    bool success = false;
    bool speaker_started = false;
    uint8_t *buffer = nullptr;
    uint8_t *prebuffer = nullptr;

    do {
        const size_t body_size = strlen(body);

        if (esp_http_client_open(client, (int)body_size)
            != ESP_OK) {
            ESP_LOGE("RIA_STREAM", "HTTP open failed");
            break;
        }

        size_t sent = 0;

        while (sent < body_size) {
            int n = esp_http_client_write(
                client, body + sent, (int)(body_size - sent)
            );

            if (n <= 0)
                break;

            sent += (size_t)n;
        }

        if (sent != body_size) {
            ESP_LOGE("RIA_STREAM", "Request write failed");
            break;
        }

        int64_t start_us = esp_timer_get_time();

        esp_http_client_fetch_headers(client);

        int status = esp_http_client_get_status_code(client);
        int64_t length =
            esp_http_client_get_content_length(client);

        ESP_LOGI(
            "RIA_STREAM",
            "HTTP=%d, WAV=%lld bytes, headers=%lld ms",
            status,
            (long long)length,
            (long long)((esp_timer_get_time()-start_us)/1000)
        );

        if (status != 200 ||
            length < 44 ||
            length > 2 * 1024 * 1024) {
            break;
        }

        buffer = (uint8_t *)heap_caps_malloc(
            8192,
            MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
        );

        if (!buffer) {
            ESP_LOGE("RIA_STREAM", "Receive allocation failed");
            break;
        }

        // Fetch exactly the 44-byte WAV header.
        size_t header_used = 0;

        while (header_used < 44) {
            int n = esp_http_client_read(
                client,
                (char *)buffer + header_used,
                (int)(44 - header_used)
            );

            if (n <= 0)
                break;

            header_used += (size_t)n;
        }

        if (header_used != 44 ||
            memcmp(buffer, "RIFF", 4) ||
            memcmp(buffer + 8, "WAVE", 4) ||
            memcmp(buffer + 12, "fmt ", 4) ||
            memcmp(buffer + 36, "data", 4)) {
            ESP_LOGE("RIA_STREAM", "Invalid WAV header");
            break;
        }

        uint32_t riff_size = 0;
        uint32_t fmt_size = 0;
        uint32_t sample_rate = 0;
        uint32_t byte_rate = 0;
        uint32_t pcm_bytes = 0;
        uint16_t format = 0;
        uint16_t channels = 0;
        uint16_t alignment = 0;
        uint16_t bits = 0;

        memcpy(&riff_size, buffer + 4, 4);
        memcpy(&fmt_size, buffer + 16, 4);
        memcpy(&format, buffer + 20, 2);
        memcpy(&channels, buffer + 22, 2);
        memcpy(&sample_rate, buffer + 24, 4);
        memcpy(&byte_rate, buffer + 28, 4);
        memcpy(&alignment, buffer + 32, 2);
        memcpy(&bits, buffer + 34, 2);
        memcpy(&pcm_bytes, buffer + 40, 4);

        if (riff_size != (uint32_t)(length - 8) ||
            fmt_size != 16 ||
            format != 1 ||
            channels != 1 ||
            sample_rate != 48000 ||
            byte_rate != 96000 ||
            alignment != 2 ||
            bits != 16 ||
            pcm_bytes == 0 ||
            (pcm_bytes % 2) != 0 ||
            pcm_bytes != (uint32_t)(length - 44)) {
            ESP_LOGE("RIA_STREAM", "Unsupported WAV format");
            break;
        }

        // RIA_STREAM_PREBUFFER_V1
        // Buffer one second of PCM before starting playback.
        // 48000 samples * 2 bytes = 96000 bytes.
        //
        // This prototype intentionally leaves the existing
        // playback loop unchanged until prebuffer ownership
        // and consumption are integrated safely.
        static const size_t RIA_PREBUFFER_BYTES = 96000;

        ESP_LOGI(
            "RIA_STREAM",
            "Prebuffer target: %u PCM bytes",
            (unsigned)RIA_PREBUFFER_BYTES
        );

        // RIA_REAL_PREBUFFER_V1
        // Keep speaker inactive until the initial PCM is loaded.
        size_t prebuffer_target = pcm_bytes;

        if (prebuffer_target > RIA_PREBUFFER_BYTES)
            prebuffer_target = RIA_PREBUFFER_BYTES;

        prebuffer = (uint8_t *)heap_caps_malloc(
            RIA_PREBUFFER_BYTES,
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
        );

        if (!prebuffer) {
            ESP_LOGE("RIA_STREAM", "Prebuffer allocation failed");
            break;
        }

        size_t prebuffer_used = 0;

        while (prebuffer_used < prebuffer_target) {
            int n = esp_http_client_read(
                client,
                (char *)prebuffer + prebuffer_used,
                (int)(prebuffer_target - prebuffer_used)
            );

            if (n <= 0) {
                ESP_LOGE(
                    "RIA_STREAM",
                    "Prebuffer download incomplete"
                );
                break;
            }

            prebuffer_used += (size_t)n;
        }

        if (prebuffer_used != prebuffer_target)
            break;

        ESP_LOGI(
            "RIA_STREAM",
            "Prebuffer ready: %u bytes",
            (unsigned)prebuffer_used
        );

        if (!ria_stream_begin()) {
            ESP_LOGE("RIA_STREAM", "Speaker start failed");
            break;
        }

        speaker_started = true;

        ESP_LOGI(
            "RIA_STREAM",
            "Streaming %u PCM bytes",
            (unsigned)pcm_bytes
        );

        if (!ria_stream_write(prebuffer, prebuffer_used)) {
            ESP_LOGE("RIA_STREAM", "Prebuffer playback failed");
            break;
        }

        size_t received = prebuffer_used;
        size_t pending = 0;
        int64_t first_audio_us = 0;

        while (received < pcm_bytes) {
            size_t wanted = pcm_bytes - received;

            if (wanted > 8192 - pending)
                wanted = 8192 - pending;

            int n = esp_http_client_read(
                client,
                (char *)buffer + pending,
                (int)wanted
            );

            if (n <= 0)
                break;

            received += (size_t)n;

            size_t available = pending + (size_t)n;
            size_t playable = available & ~(size_t)1;

            if (playable > 0) {
                if (first_audio_us == 0) {
                    first_audio_us = esp_timer_get_time();
                    ESP_LOGI(
                        "RIA_STREAM",
                        "First PCM received after %lld ms",
                        (long long)(
                            (first_audio_us - start_us) / 1000
                        )
                    );
                }

                if (!ria_stream_write(buffer, playable)) {
                    ESP_LOGE(
                        "RIA_STREAM", "Speaker write failed"
                    );
                    break;
                }
            }

            pending = available - playable;

            if (pending == 1)
                buffer[0] = buffer[playable];
        }

        if (received != pcm_bytes || pending != 0) {
            ESP_LOGE(
                "RIA_STREAM",
                "Incomplete playback: %u/%u",
                (unsigned)received,
                (unsigned)pcm_bytes
            );
            break;
        }

        ESP_LOGI(
            "RIA_STREAM",
            "Playback complete: %u bytes",
            (unsigned)received
        );

        success = true;

    } while (false);

    if (speaker_started)
        ria_stream_end();

    if (prebuffer)
        heap_caps_free(prebuffer);

    if (buffer)
        heap_caps_free(buffer);

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    cJSON_free(body);

    return success;
}
