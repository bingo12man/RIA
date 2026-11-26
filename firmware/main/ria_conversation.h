#pragma once

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_err.h"
#include "cJSON.h"

#include "private/device_config.h"

// Send recognized text to the existing RIA AI pipeline.
// Returns ESP_OK only when the bridge responds HTTP 200.
static esp_err_t ria_send_conversation(
    const char *text,
    char *reply_out,
    size_t reply_capacity
)
{
    if (!text || !text[0] ||
        !reply_out || reply_capacity == 0)
        return ESP_ERR_INVALID_ARG;

    reply_out[0] = '\0';

    if (strlen(text) > 1000)
        return ESP_ERR_INVALID_SIZE;

    cJSON *payload = cJSON_CreateObject();
    if (!payload)
        return ESP_ERR_NO_MEM;

    cJSON_AddStringToObject(payload, "text", text);
    char *body = cJSON_PrintUnformatted(payload);
    cJSON_Delete(payload);

    if (!body)
        return ESP_ERR_NO_MEM;

    esp_http_client_config_t config = {};
    config.url = "http://192.168.0.104:8041/command";
    config.timeout_ms = 100000;
    config.buffer_size = 1024;
    config.buffer_size_tx = 1024;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (!client) {
        cJSON_free(body);
        return ESP_FAIL;
    }

    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(
        client, "Content-Type", "application/json"
    );
    esp_http_client_set_header(
        client, "X-RIA-Token", RIA_DEVICE_TOKEN
    );
    esp_http_client_set_post_field(
        client, body, (int)strlen(body)
    );

    esp_err_t err = esp_http_client_open(
        client, (int)strlen(body)
    );

    if (err != ESP_OK) {
        ESP_LOGE("RIA_LLM", "Connect failed: %s",
                 esp_err_to_name(err));
        esp_http_client_cleanup(client);
        cJSON_free(body);
        return err;
    }

    int remaining = (int)strlen(body);
    const char *ptr = body;

    while (remaining > 0) {
        int n = esp_http_client_write(
            client, ptr, remaining
        );

        if (n <= 0) {
            esp_http_client_close(client);
            esp_http_client_cleanup(client);
            cJSON_free(body);
            return ESP_FAIL;
        }

        ptr += n;
        remaining -= n;
    }

    esp_http_client_fetch_headers(client);

    int status =
        esp_http_client_get_status_code(client);

    char response[4096] = {};
    size_t used = 0;

    while (used < sizeof(response) - 1) {
        int n = esp_http_client_read(
            client,
            response + used,
            (int)(sizeof(response) - 1 - used)
        );

        if (n <= 0)
            break;

        used += n;
    }

    response[used] = '\0';

    ESP_LOGI("RIA_LLM", "HTTP status=%d", status);

    if (status == 200) {
        cJSON *result = cJSON_Parse(response);

        if (result) {
            cJSON *reply =
                cJSON_GetObjectItemCaseSensitive(
                    result, "reply"
                );

            if (cJSON_IsString(reply) &&
                reply->valuestring != nullptr) {

                const size_t reply_len =
                    strlen(reply->valuestring);

                ESP_LOGI(
                    "RIA_LLM",
                    "RIA says: %s",
                    reply->valuestring
                );

                if (reply_len > 0 &&
                    reply_len < reply_capacity) {

                    memcpy(
                        reply_out,
                        reply->valuestring,
                        reply_len + 1
                    );

                } else {
                    ESP_LOGE(
                        "RIA_LLM",
                        "Reply empty or exceeds output buffer"
                    );
                    err = ESP_FAIL;
                }
            } else {
                ESP_LOGE(
                    "RIA_LLM", "Missing reply field"
                );
                err = ESP_FAIL;
            }

            cJSON_Delete(result);
        } else {
            ESP_LOGE(
                "RIA_LLM", "Invalid JSON response"
            );
            err = ESP_FAIL;
        }
    } else {
        ESP_LOGE(
            "RIA_LLM", "Backend response: %.200s",
            response
        );
        err = ESP_FAIL;
    }

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    cJSON_free(body);

    return status == 200 ? err : ESP_FAIL;
}
