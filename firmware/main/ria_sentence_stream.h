#pragma once

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_http_client.h"
#include "esp_heap_caps.h"

#include "cJSON.h"
#include "esp_es8311_port.h"
#include "private/device_config.h"

// RIA A3.32.94 — Optional sentence PCM streaming.
// Transport: 4-byte LE length + 48 kHz mono PCM16 segment.
// Zero-length frame indicates successful completion.

static bool ria_sentence_stream_speech(const char *text, const char *emotion)
{
    if (!text || !text[0] || strlen(text) > 500)
        return false;

    cJSON *json = cJSON_CreateObject();
    if (!json)
        return false;

    cJSON_AddStringToObject(json, "text", text);
    cJSON_AddStringToObject(
        json, "emotion",
        (emotion && emotion[0]) ? emotion : "neutral"
    );
    char *body = cJSON_PrintUnformatted(json);
    cJSON_Delete(json);

    if (!body)
        return false;

    esp_http_client_config_t config = {};
    config.url = "http://192.168.0.104:8041/speak-stream";
    config.timeout_ms = 120000;
    config.buffer_size = 8192;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (!client) {
        cJSON_free(body);
        return false;
    }

    bool success = false;
    bool speaker_started = false;

    do {
        esp_http_client_set_method(client, HTTP_METHOD_POST);
        esp_http_client_set_header(
            client, "Content-Type", "application/json"
        );
        esp_http_client_set_header(
            client, "X-RIA-Token", RIA_DEVICE_TOKEN
        );

        const size_t body_size = strlen(body);

        if (esp_http_client_open(client, (int)body_size) != ESP_OK)
            break;

        size_t sent = 0;

        while (sent < body_size) {
            int n = esp_http_client_write(
                client,
                body + sent,
                (int)(body_size - sent)
            );

            if (n <= 0)
                break;

            sent += (size_t)n;
        }

        if (sent != body_size)
            break;

        esp_http_client_fetch_headers(client);

        if (esp_http_client_get_status_code(client) != 200) {
            ESP_LOGE("RIA_SENTENCE", "Streaming endpoint unavailable");
            break;
        }

        uint8_t header[4];
        uint8_t buffer[8192];

        uint32_t segment_count = 0;
        size_t total_bytes = 0;

        while (true) {
            size_t used = 0;

            while (used < 4) {
                int n = esp_http_client_read(
                    client, (char *)header + used, 4 - used
                );

                if (n <= 0)
                    break;

                used += (size_t)n;
            }

            if (used != 4)
                break;

            uint32_t remaining =
                (uint32_t)header[0] |
                ((uint32_t)header[1] << 8) |
                ((uint32_t)header[2] << 16) |
                ((uint32_t)header[3] << 24);

            if (remaining == 0) {
                success = segment_count > 0;
                break;
            }

            if (remaining > 10000000 || (remaining & 1))
                break;

            // RIA_A33324_PSRAM_BUFFER
            // Diagnostic: fully receive one PCM sentence
            // before writing any of it to the speaker.
            uint8_t *segment_pcm = (uint8_t *)heap_caps_malloc(
                remaining,
                MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
            );

            if (!segment_pcm) {
                ESP_LOGE("RIA_SENTENCE", "PSRAM allocation failed");
                break;
            }

            const uint32_t segment_size = remaining;
            uint32_t received_total = 0;
            bool playback_failed = false;

            while (received_total < segment_size) {
                uint32_t wanted = segment_size - received_total;

                if (wanted > 8192)
                    wanted = 8192;

                int n = esp_http_client_read(
                    client,
                    (char *)segment_pcm + received_total,
                    (int)wanted
                );

                if (n <= 0) {
                    playback_failed = true;
                    break;
                }

                received_total += (uint32_t)n;
            }

            if (!playback_failed) {
                if (!speaker_started) {
                    if (!ria_stream_begin()) {
                        playback_failed = true;
                    } else {
                        speaker_started = true;
                    }
                }
            }

            if (!playback_failed) {
                // RIA_A33327_TIMING
                int64_t playback_start_us = esp_timer_get_time();

                ESP_LOGI(
                    "RIA_SENTENCE",
                    "Buffered %lu PCM bytes before playback",
                    (unsigned long)segment_size
                );

                playback_failed = !ria_stream_write(
                    segment_pcm, segment_size
                );

                ESP_LOGI(
                    "RIA_TIMING",
                    "Playback took %lld ms for %lu bytes",
                    (long long)(
                        (esp_timer_get_time() -
                         playback_start_us) / 1000
                    ),
                    (unsigned long)segment_size
                );
            }

            heap_caps_free(segment_pcm);

            if (playback_failed) {
                ESP_LOGE(
                    "RIA_SENTENCE",
                    "Buffered sentence playback failed"
                );
                break;
            }

            total_bytes += segment_size;

            ++segment_count;
            ESP_LOGI(
                "RIA_SENTENCE",
                "Completed segment %lu",
                (unsigned long)segment_count
            );
        }

        ESP_LOGI(
            "RIA_SENTENCE",
            "Segments=%lu, PCM bytes=%u, success=%d",
            (unsigned long)segment_count,
            (unsigned)total_bytes,
            (int)success
        );

    } while (false);

    if (speaker_started)
        ria_stream_end();

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    cJSON_free(body);

    return success;
}
