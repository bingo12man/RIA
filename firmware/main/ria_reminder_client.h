#pragma once

// RIA_REMINDER_CLIENT_V1
// Authenticated claim/acknowledgement client.
// Must only be called from RIA's audio task.

#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdint>

#include "esp_http_client.h"
#include "esp_log.h"
#include "cJSON.h"
#include "private/device_config.h"

struct RiaReminder {
    int id;
    int64_t due_at;
    char title[201];
    char token[33];
};

static bool ria_reminder_http(
    const char *path,
    const char *post_body,
    char *response,
    size_t capacity,
    int *status
) {
    if (!path || !response || capacity < 2 || !status)
        return false;

    *status = 0;
    response[0] = '\0';

    char url[160];
    int len = snprintf(
        url, sizeof(url),
        "http://192.168.0.104:8041%s", path
    );
    if (len <= 0 || (size_t)len >= sizeof(url))
        return false;

    esp_http_client_config_t config = {};
    config.url = url;
    config.timeout_ms = 5000;
    config.buffer_size = 2048;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (!client)
        return false;

    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(
        client, "X-RIA-Token", RIA_DEVICE_TOKEN
    );
    esp_http_client_set_header(
        client, "Content-Type", "application/json"
    );

    const char *body = post_body ? post_body : "";
    size_t body_len = strlen(body);
    bool ok = false;

    do {
        if (esp_http_client_open(client, (int)body_len) != ESP_OK)
            break;

        size_t sent = 0;
        while (sent < body_len) {
            int n = esp_http_client_write(
                client, body + sent, (int)(body_len - sent)
            );
            if (n <= 0)
                break;
            sent += (size_t)n;
        }
        if (sent != body_len)
            break;

        esp_http_client_fetch_headers(client);
        *status = esp_http_client_get_status_code(client);

        // RIA_REMINDER_HTTP_COMPLETE_V2
        const int64_t expected =
            esp_http_client_get_content_length(client);

        // Reminder bridge must return a bounded JSON body.
        // Reject chunked/unknown-length responses for now.
        if (expected < 0 ||
            expected == 0 ||
            expected >= (int64_t)capacity)
            break;

        size_t used = 0;
        bool read_error = false;

        // RIA_REMINDER_HTTP_RETRY_V3
        int empty_reads = 0;

        while (used < (size_t)expected) {
            int n = esp_http_client_read(
                client,
                response + used,
                (int)((size_t)expected - used)
            );

            if (n < 0) {
                read_error = true;
                break;
            }

            if (n == 0) {
                ++empty_reads;

                if (empty_reads >= 3) {
                    read_error = true;
                    break;
                }

                vTaskDelay(pdMS_TO_TICKS(100));
                continue;
            }

            empty_reads = 0;
            used += (size_t)n;
        }

        response[used] = '\0';

        if (read_error || used != (size_t)expected)
            break;

        ok = true;
    } while (false);

    esp_http_client_cleanup(client);
    return ok;
}


// RIA_INTERACTIVE_REMINDERS_V1
static bool ria_send_reminder_user_action(
    const RiaReminder &reminder,
    int action,
    int seconds = 0
) {
    const char *action_name =
        action == 1 ? "done" :
        action == 2 ? "snooze" :
        action == 3 ? "skip" : nullptr;

    if (!action_name)
        return false;

    cJSON *body = cJSON_CreateObject();
    if (!body)
        return false;

    char request_id[80] = {};
    snprintf(
        request_id, sizeof(request_id),
        "orbit_%d_%lu_%d",
        reminder.id,
        (unsigned long)xTaskGetTickCount(),
        action
    );

    cJSON_AddNumberToObject(body, "id", reminder.id);
    cJSON_AddStringToObject(
        body, "expected_title", reminder.title
    );
    cJSON_AddNumberToObject(
        body, "expected_due_at", (double)reminder.due_at
    );
    cJSON_AddStringToObject(
        body, "action", action_name
    );
    cJSON_AddStringToObject(
        body, "request_id", request_id
    );

    // RIA_REMINDER_VOICE_SECONDS_V1
    if (action == 2) {
        if (seconds > 0)
            cJSON_AddNumberToObject(body, "seconds", seconds);
        else
            cJSON_AddNumberToObject(body, "minutes", 5);
    }

    char *payload = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);

    if (!payload)
        return false;

    char response[768] = {};
    int status = 0;

    bool ok = ria_reminder_http(
        "/reminders/user-action",
        payload,
        response, sizeof(response), &status
    );

    free(payload);

    if (!ok || status != 200)
        return false;

    cJSON *root = cJSON_Parse(response);
    bool success = false;

    if (root) {
        cJSON *result = cJSON_GetObjectItemCaseSensitive(
            root, "success"
        );
        success = cJSON_IsTrue(result);
        cJSON_Delete(root);
    }

    return success;
}

static bool ria_claim_reminder(RiaReminder *out) {
    if (!out)
        return false;

    memset(out, 0, sizeof(*out));

    char response[1024] = {};
    int status = 0;

    if (!ria_reminder_http(
        "/reminders/claim", "{}", response,
        sizeof(response), &status
    )) {
        ESP_LOGW("RIA_REMINDER", "Claim connection failed");
        return false;
    }

    if (status != 200) {
        ESP_LOGW(
            "RIA_REMINDER", "Claim HTTP status: %d", status
        );
        return false;
    }

    cJSON *root = cJSON_Parse(response);
    if (!root)
        return false;

    bool claimed = false;

    do {
        cJSON *item = cJSON_GetObjectItemCaseSensitive(
            root, "reminder"
        );
        if (!cJSON_IsObject(item))
            break;

        cJSON *id = cJSON_GetObjectItemCaseSensitive(item, "id");
        cJSON *due = cJSON_GetObjectItemCaseSensitive(
            item, "due_at"
        );
        cJSON *title = cJSON_GetObjectItemCaseSensitive(
            item, "title"
        );
        cJSON *token = cJSON_GetObjectItemCaseSensitive(
            item, "delivery_token"
        );

        if (!cJSON_IsNumber(id) ||
            !cJSON_IsNumber(due) ||
            !cJSON_IsString(title) ||
            !cJSON_IsString(token))
            break;

        if (id->valuedouble < 1 ||
            id->valuedouble > 2147483647.0 ||
            due->valuedouble < 1 ||
            due->valuedouble > 9007199254740991.0)
            break;

        if (id->valuedouble != (double)id->valueint ||
            due->valuedouble !=
                (double)(int64_t)due->valuedouble)
            break;

        size_t title_len = strlen(title->valuestring);
        size_t token_len = strlen(token->valuestring);

        if (title_len == 0 || title_len > 200 ||
            token_len != 32)
            break;

        bool valid_token = true;
        for (size_t i = 0; i < 32; ++i) {
            char c = token->valuestring[i];
            if (!((c >= '0' && c <= '9') ||
                  (c >= 'a' && c <= 'f'))) {
                valid_token = false;
                break;
            }
        }
        if (!valid_token)
            break;

        out->id = id->valueint;
        out->due_at = (int64_t)due->valuedouble;
        memcpy(out->title, title->valuestring, title_len + 1);
        memcpy(out->token, token->valuestring, 33);
        claimed = true;
    } while (false);

    cJSON_Delete(root);
    return claimed;
}

static bool ria_acknowledge_reminder(
    const RiaReminder &reminder
) {
    cJSON *body = cJSON_CreateObject();
    if (!body)
        return false;

    cJSON_AddNumberToObject(body, "id", reminder.id);
    cJSON_AddNumberToObject(
        body, "due_at", (double)reminder.due_at
    );
    cJSON_AddStringToObject(
        body, "delivery_token", reminder.token
    );

    char *payload = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);
    if (!payload)
        return false;

    char response[384] = {};
    int status = 0;

    bool ok = ria_reminder_http(
        "/reminders/acknowledge",
        payload, response, sizeof(response), &status
    );
    free(payload);

    if (!ok || status != 200) {
        ESP_LOGW(
            "RIA_REMINDER",
            "Acknowledgement failed, HTTP=%d", status
        );
        return false;
    }

    cJSON *root = cJSON_Parse(response);
    if (!root)
        return false;

    cJSON *delivery_status =
        cJSON_GetObjectItemCaseSensitive(
            root, "delivery_status"
        );

    bool delivered =
        cJSON_IsString(delivery_status) &&
        strcmp(delivery_status->valuestring, "delivered") == 0;

    cJSON_Delete(root);
    return delivered;
}


// RIA_ORBIT_UPCOMING_V1
static bool ria_fetch_upcoming(
    char titles[2][48],
    char times[2][16]
) {
    char response[1024] = {};
    int status = 0;

    if (!ria_reminder_http(
        "/reminders/upcoming", "{}",
        response, sizeof(response), &status
    ) || status != 200) {
        return false;
    }

    cJSON *root = cJSON_Parse(response);
    if (!root)
        return false;

    cJSON *items = cJSON_GetObjectItemCaseSensitive(
        root, "items"
    );

    if (!cJSON_IsArray(items) ||
        cJSON_GetArraySize(items) > 2) {
        cJSON_Delete(root);
        return false;
    }

    const int count = cJSON_GetArraySize(items);

    for (int i = 0; i < 2; ++i) {
        if (i >= count) {
            snprintf(
                titles[i], 48,
                "%s", i == 0 ? "No reminders" : ""
            );
            times[i][0] = '\0';
            continue;
        }

        cJSON *item = cJSON_GetArrayItem(items, i);
        cJSON *title = cJSON_GetObjectItemCaseSensitive(
            item, "title"
        );
        cJSON *time = cJSON_GetObjectItemCaseSensitive(
            item, "time"
        );

        if (!cJSON_IsString(title) ||
            !cJSON_IsString(time)) {
            cJSON_Delete(root);
            return false;
        }

        snprintf(titles[i], 48, "%s", title->valuestring);
        snprintf(times[i], 16, "%s", time->valuestring);
    }

    cJSON_Delete(root);
    return true;
}



// RIA_ORBIT_INFOBAR_V1
static bool ria_fetch_device_info(
    char clock_text[24],
    char date_text[40],
    char weather_text[48]
) {
    char response[512] = {};
    int status = 0;

    if (!ria_reminder_http(
        "/device/info", "{}",
        response, sizeof(response), &status
    ) || status != 200) {
        return false;
    }

    cJSON *root = cJSON_Parse(response);
    if (!root)
        return false;

    cJSON *clock = cJSON_GetObjectItemCaseSensitive(root, "clock");
    cJSON *date = cJSON_GetObjectItemCaseSensitive(root, "date");
    cJSON *weather = cJSON_GetObjectItemCaseSensitive(root, "weather");

    bool valid =
        cJSON_IsString(clock) &&
        cJSON_IsString(date) &&
        cJSON_IsString(weather);

    if (valid) {
        snprintf(clock_text, 24, "%s", clock->valuestring);
        snprintf(date_text, 40, "%s", date->valuestring);
        snprintf(weather_text, 48, "%s", weather->valuestring);
    }

    cJSON_Delete(root);
    return valid;
}
