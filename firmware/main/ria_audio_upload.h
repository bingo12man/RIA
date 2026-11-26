#pragma once

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "esp_http_client.h"
#include "esp_timer.h"
#include "cJSON.h"
#include "esp_log.h"

#include "ria_wav.h"
#include "private/device_config.h"

static esp_err_t ria_upload_pcm(
    const uint8_t *pcm,
    size_t pcm_size,
    char *transcript,
    size_t transcript_capacity
) {
    if (!pcm || pcm_size == 0 ||
        pcm_size > 5760000 ||
        (pcm_size % 2) != 0 ||
        !transcript || transcript_capacity == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    transcript[0] = '\0';

    const char *boundary = "ria-esp32-audio-v1";

    char prefix[256];
    int prefix_len = snprintf(
        prefix, sizeof(prefix),
        "--%s\r\n"
        "Content-Disposition: form-data; "
        "name=\"file\"; filename=\"ria.wav\"\r\n"
        "Content-Type: audio/wav\r\n"
        "\r\n",
        boundary
    );

    if (prefix_len < 0 ||
        (size_t)prefix_len >= sizeof(prefix)) {
        return ESP_ERR_INVALID_SIZE;
    }

    char suffix[100];
    int suffix_len = snprintf(
        suffix, sizeof(suffix),
        "\r\n--%s--\r\n",
        boundary
    );

    if (suffix_len < 0 ||
        (size_t)suffix_len >= sizeof(suffix)) {
        return ESP_ERR_INVALID_SIZE;
    }

    uint8_t wav_header[44];
    // RIA_UPLOAD_16KHZ_FIR_V1
    // Microphone captures 48 kHz PCM16 mono.
    // Upload is low-pass filtered and decimated to 16 kHz.
    const size_t input_samples = pcm_size / 2;
    const size_t output_samples =
        (input_samples + 2) / 3;
    const size_t upload_pcm_size =
        output_samples * 2;

    // Preserve the existing bridge's 2 MiB limit.
    if (upload_pcm_size > 2 * 1024 * 1024)
        return ESP_ERR_INVALID_SIZE;

    ria_make_wav_header(
        wav_header,
        (uint32_t)upload_pcm_size,
        16000
    );

    size_t total =
        (size_t)prefix_len + 44 + upload_pcm_size +
        (size_t)suffix_len;

    esp_http_client_config_t config = {};
    config.url =
        "http://192.168.0.104:8041/audio/transcribe";
    config.timeout_ms = 100000;
    config.buffer_size = 1024;
    config.buffer_size_tx = 8192;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (!client) {
        return ESP_FAIL;
    }

    char content_type[120];
    snprintf(
        content_type, sizeof(content_type),
        "multipart/form-data; boundary=%s",
        boundary
    );

    esp_http_client_set_method(
        client, HTTP_METHOD_POST
    );
    esp_http_client_set_header(
        client, "Content-Type", content_type
    );
    esp_http_client_set_header(
        client, "X-RIA-Token", RIA_DEVICE_TOKEN
    );

    int64_t connection_start_us = esp_timer_get_time();

    esp_err_t err = esp_http_client_open(
        client, (int)total
    );

    ESP_LOGI("RIA_UPLOAD_TIMING", "HTTP connection: %lld ms", (long long)((esp_timer_get_time() - connection_start_us) / 1000));

    if (err != ESP_OK) {
        ESP_LOGE(
            "RIA_UPLOAD", "Open failed: %s",
            esp_err_to_name(err)
        );
        esp_http_client_cleanup(client);
        return err;
    }

    auto send_all = [&](const char *data, size_t size) -> bool {
        size_t sent = 0;

        while (sent < size) {
            int written = esp_http_client_write(
                client,
                data + sent,
                (int)(size - sent)
            );

            if (written <= 0) {
                return false;
            }

            sent += written;
        }

        return true;
    };


    // 31-tap Hamming-windowed low-pass FIR.
    // Approximate 6.96 kHz cutoff at 48 kHz input.
    // Anti-alias filtering precedes 3:1 decimation.
    static const float fir[31] = {
         0.001511968f,  0.000383491f, -0.001938522f,
        -0.004441717f, -0.003775140f,  0.003047944f,
         0.013233563f,  0.016518700f,  0.002515542f,
        -0.026369327f, -0.048395347f, -0.032487886f,
         0.038420162f,  0.147960422f,  0.248878624f,
         0.289875046f,  0.248878624f,  0.147960422f,
         0.038420162f, -0.032487886f, -0.048395347f,
        -0.026369327f,  0.002515542f,  0.016518700f,
         0.013233563f,  0.003047944f, -0.003775140f,
        -0.004441717f, -0.001938522f,  0.000383491f,
         0.001511968f
    };

    auto send_downsampled = [&]() -> bool {
        // Input buffer is PSRAM allocated and 16-bit aligned.
        const int16_t *samples =
            (const int16_t *)pcm;

        // Only 1 KiB temporary buffer on the task stack.
        int16_t chunk[512];
        size_t filled = 0;
        size_t emitted = 0;

        for (size_t out = 0; out < output_samples; ++out) {
            const int64_t center = (int64_t)out * 3;
            float filtered = 0.0f;

            for (int tap = 0; tap < 31; ++tap) {
                int64_t index =
                    center + tap - 15;

                if (index < 0)
                    index = 0;

                if (index >= (int64_t)input_samples)
                    index = (int64_t)input_samples - 1;

                filtered +=
                    fir[tap] * (float)samples[index];
            }

            if (filtered > 32767.0f)
                filtered = 32767.0f;

            if (filtered < -32768.0f)
                filtered = -32768.0f;

            int32_t rounded = (int32_t)(
                filtered >= 0.0f
                    ? filtered + 0.5f
                    : filtered - 0.5f
            );

            chunk[filled++] = (int16_t)rounded;

            if (filled == 512) {
                if (!send_all(
                    (const char *)chunk,
                    filled * sizeof(int16_t)))
                    return false;

                emitted += filled * sizeof(int16_t);
                filled = 0;
            }
        }

        if (filled > 0) {
            if (!send_all(
                (const char *)chunk,
                filled * sizeof(int16_t)))
                return false;

            emitted += filled * sizeof(int16_t);
        }

        ESP_LOGI(
            "RIA_UPLOAD",
            "Resampled 48000 -> 16000 Hz: %u -> %u bytes",
            (unsigned)pcm_size,
            (unsigned)emitted
        );

        return emitted == upload_pcm_size;
    };

    int64_t upload_start_us = esp_timer_get_time();

    bool ok =
        send_all(prefix, (size_t)prefix_len) &&
        send_all((const char *)wav_header, 44) &&
        send_downsampled() &&
        send_all(suffix, (size_t)suffix_len);

    ESP_LOGI("RIA_UPLOAD_TIMING", "Audio upload write: %lld ms", (long long)((esp_timer_get_time() - upload_start_us) / 1000));

    if (!ok) {
        ESP_LOGE("RIA_UPLOAD", "Upload write failed");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }

    int64_t whisper_wait_us = esp_timer_get_time();

    int header_len =
        esp_http_client_fetch_headers(client);

    ESP_LOGI("RIA_UPLOAD_TIMING", "Whisper response wait: %lld ms", (long long)((esp_timer_get_time() - whisper_wait_us) / 1000));

    int status =
        esp_http_client_get_status_code(client);

    ESP_LOGI(
        "RIA_UPLOAD",
        "HTTP status=%d, headers=%d",
        status, header_len
    );

    char response[1025] = {};
    size_t used = 0;

    while (used < sizeof(response) - 1) {
        int n = esp_http_client_read(
            client,
            response + used,
            (int)(sizeof(response) - 1 - used)
        );

        if (n <= 0) {
            break;
        }

        used += n;
    }

    response[used] = '\0';

    ESP_LOGI(
        "RIA_UPLOAD", "Response: %s",
        response
    );

    bool valid_response = false;

    if (status == 200) {
        cJSON *result = cJSON_Parse(response);

        if (result) {
            cJSON *text = cJSON_GetObjectItemCaseSensitive(
                result, "text"
            );
            cJSON *rejected = cJSON_GetObjectItemCaseSensitive(
                result, "rejected"
            );

            if (cJSON_IsString(text) &&
                !cJSON_IsTrue(rejected)) {
                size_t length = strlen(text->valuestring);

                if (length < transcript_capacity) {
                    memcpy(
                        transcript,
                        text->valuestring,
                        length + 1
                    );
                    valid_response = true;
                } else {
                    ESP_LOGE(
                        "RIA_UPLOAD",
                        "Transcription buffer too small"
                    );
                }
            }

            cJSON_Delete(result);
        }
    }

    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    return valid_response ? ESP_OK : ESP_FAIL;
}
