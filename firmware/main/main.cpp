#include "esp_heap_caps.h"
#include <stdio.h>

#include "nvs_flash.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

#include "driver/gpio.h"

#include "driver/i2c_master.h"

#include "esp_io_expander_tca9554.h"

#include "lvgl.h"
#include "demos/lv_demos.h"

#include "esp_lvgl_port.h"

#include "lvgl_ui.h"
#include "ria_home.h"

// RIA_MEMORY_UI_BRIDGE_V1
// UI-only integration. No HTTP or memory writes.
// Disabled until pending proposal transport is connected.
#ifndef RIA_ENABLE_MEMORY_APPROVAL_UI
#define RIA_ENABLE_MEMORY_APPROVAL_UI 1
#endif

#if RIA_ENABLE_MEMORY_APPROVAL_UI

static bool ria_show_memory_confirmation(
    const char *proposal_text
) {
    if (!proposal_text || !proposal_text[0])
        return false;

    if (!lvgl_port_lock(pdMS_TO_TICKS(1000)))
        return false;

    ria_memory_confirm_show(proposal_text);

    lvgl_port_unlock();
    return true;
}

static int ria_read_memory_confirmation(void)
{
    return ria_memory_confirm_take_decision();
}

#endif
// END RIA_MEMORY_UI_BRIDGE_V1


#include "ria_pcm_ring_test.h"
#include "ria_pcm_ring_concurrency_test.h"

#include "esp_check.h"
#include "esp_log.h"

#include "iot_button.h"
#include "button_gpio.h"

#include "esp_axp2101_port.h"
#include "esp_camera_port.h"
#include "esp_es8311_port.h"
#include "esp_pcf85063_port.h"
#include "esp_qmi8658_port.h"
#include "esp_sdcard_port.h"
#include "esp_wifi_port.h"
#include "esp_http_client.h"
#include "ria_audio_upload.h"
#include "ria_conversation.h"
#include "ria_speech_download.h"
#include "ria_speech_stream.h"
#include "ria_sentence_stream.h"
#include "ria_reminder_client.h"


// RIA_MEMORY_TRANSPORT_A328
// Preview-only device transport. No memory database writes.
// Uses the same Mac bridge and device token as reminders.

#if RIA_ENABLE_MEMORY_APPROVAL_UI

static char ria_memory_active_id[33] = {};
static int ria_memory_queued_decision = 0;
static TickType_t ria_memory_last_poll = 0;

static bool ria_memory_get_pending(
    char *output,
    size_t capacity,
    int *status
) {
    if (!output || capacity < 2 || !status)
        return false;

    output[0] = '\0';
    *status = 0;

    esp_http_client_config_t config = {};
    config.url =
        "http://192.168.0.104:8041/memory/pending";
    config.timeout_ms = 3000;
    config.buffer_size = 1024;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (!client)
        return false;

    esp_http_client_set_method(
        client, HTTP_METHOD_GET
    );

    esp_http_client_set_header(
        client, "X-RIA-Token", RIA_DEVICE_TOKEN
    );

    bool ok = false;

    do {
        if (esp_http_client_open(client, 0) != ESP_OK)
            break;

        esp_http_client_fetch_headers(client);

        *status =
            esp_http_client_get_status_code(client);

        if (*status != 200)
            break;

        int64_t length =
            esp_http_client_get_content_length(client);

        // Only accept bounded, known-length JSON.
        if (length <= 0 ||
            length >= (int64_t)capacity)
            break;

        int received = esp_http_client_read_response(
            client, output, capacity - 1
        );

        if (received != length)
            break;

        output[received] = '\0';
        ok = true;

    } while (false);

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return ok;
}

static bool ria_memory_send_decision(
    const char *request_id,
    int choice
) {
    if (!request_id ||
        strlen(request_id) != 32 ||
        (choice != 1 && choice != 2))
        return false;

    cJSON *body = cJSON_CreateObject();
    if (!body)
        return false;

    cJSON_AddStringToObject(
        body, "request_id", request_id
    );

    cJSON_AddStringToObject(
        body, "decision",
        choice == 1 ? "confirm" : "cancel"
    );

    char *payload = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);

    if (!payload)
        return false;

    char response[512] = {};
    int status = 0;

    bool sent = ria_reminder_http(
        "/memory/decision",
        payload,
        response,
        sizeof(response),
        &status
    );

    free(payload);

    // RIA_MEMORY_TERMINAL_RECOVERY_V1
    // 404 = missing, 409 = resolved, 410 = expired.
    // A terminal response must not cause infinite retries.
    if (status == 404 || status == 409 || status == 410)
        return true;

    if (!sent || status != 200)
        return false;

    cJSON *result = cJSON_Parse(response);

    if (!result)
        return false;

    cJSON *success =
        cJSON_GetObjectItemCaseSensitive(
            result, "success"
        );

    cJSON *executed =
        cJSON_GetObjectItemCaseSensitive(
            result, "memory_executed"
        );

    // RIA_A33122B_MEMORY_ACK:
    // Confirm may execute a durable write or remain preview-only.
    // Cancel must never execute a memory write.
    bool executed_valid =
        cJSON_IsTrue(executed) ||
        cJSON_IsFalse(executed);

    bool ok =
        cJSON_IsTrue(success) &&
        executed_valid &&
        (ria_memory_queued_decision == 1 ||
         cJSON_IsFalse(executed));

    cJSON_Delete(result);
    return ok;
}

static void ria_memory_hide_preview(void)
{
    if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
        if (ria_memory_overlay) {
            lv_obj_add_flag(
                ria_memory_overlay,
                LV_OBJ_FLAG_HIDDEN
            );
        }
        lvgl_port_unlock();
    }
}

static void ria_memory_transport_tick(bool available)
{
    if (!available)
        return;

    TickType_t now = xTaskGetTickCount();

    if (
        now - ria_memory_last_poll <
        pdMS_TO_TICKS(3000)
    )
        return;

    ria_memory_last_poll = now;

    // The LVGL button callback records the decision.
    // Network communication happens here, in the audio task.
    int selected = ria_read_memory_confirmation();

    if (selected != 0 &&
        ria_memory_active_id[0] &&
        ria_memory_queued_decision == 0)
    {
        ria_memory_queued_decision = selected;
    }

    // Keep the request ID until the bridge acknowledges.
    // A failed request can be retried safely.
    if (ria_memory_queued_decision != 0) {
        bool accepted = ria_memory_send_decision(
            ria_memory_active_id,
            ria_memory_queued_decision
        );

        if (accepted) {
            ESP_LOGI(
                "RIA_MEMORY",
                "Preview decision acknowledged: %s",
                ria_memory_queued_decision == 1
                    ? "CONFIRM" : "CANCEL"
            );

            ria_memory_active_id[0] = '\0';
            ria_memory_queued_decision = 0;
            ria_memory_hide_preview();
        } else {
            ESP_LOGW(
                "RIA_MEMORY",
                "Preview decision not acknowledged; retrying"
            );
        }

        return;
    }

    char response[1024] = {};
    int status = 0;

    if (!ria_memory_get_pending(
        response, sizeof(response), &status
    )) {
        if (status != 404) {
            ESP_LOGW(
                "RIA_MEMORY",
                "Pending request unavailable, HTTP=%d",
                status
            );
        }
        return;
    }

    cJSON *root = cJSON_Parse(response);
    if (!root)
        return;

    cJSON *pending =
        cJSON_GetObjectItemCaseSensitive(
            root, "pending"
        );

    if (cJSON_IsFalse(pending)) {
        if (ria_memory_active_id[0]) {
            ria_memory_active_id[0] = '\0';
            ria_memory_hide_preview();
        }

        cJSON_Delete(root);
        return;
    }

    cJSON *id =
        cJSON_GetObjectItemCaseSensitive(
            root, "request_id"
        );

    cJSON *proposal =
        cJSON_GetObjectItemCaseSensitive(
            root, "proposal"
        );

    if (
        !cJSON_IsString(id) ||
        !cJSON_IsString(proposal) ||
        !id->valuestring ||
        !proposal->valuestring ||
        strlen(id->valuestring) != 32 ||
        strlen(proposal->valuestring) > 300
    ) {
        cJSON_Delete(root);
        return;
    }

    bool valid_id = true;
    for (int i = 0; i < 32; ++i) {
        char c = id->valuestring[i];
        if (!((c >= '0' && c <= '9') ||
              (c >= 'a' && c <= 'f'))) {
            valid_id = false;
            break;
        }
    }

    if (!valid_id) {
        cJSON_Delete(root);
        return;
    }

    if (strcmp(
        ria_memory_active_id,
        id->valuestring
    ) != 0) {

        if (ria_show_memory_confirmation(
            proposal->valuestring
        )) {
            snprintf(
                ria_memory_active_id,
                sizeof(ria_memory_active_id),
                "%s",
                id->valuestring
            );

            ESP_LOGI(
                "RIA_MEMORY",
                "Pending memory proposal displayed"
            );
        }
    }

    cJSON_Delete(root);
}

#endif
// END RIA_MEMORY_TRANSPORT_A328



// RIA experimental HTTP audio streaming.
// 0 = proven full-WAV playback
// 1 = experimental chunked streaming playback
#define RIA_USE_STREAMING_AUDIO 0

// RIA_SENTENCE_STREAM_A33314
#define RIA_USE_SENTENCE_STREAM_AUDIO 0


// RIA proactive reminder announcements.
// 0 = disabled, existing voice behavior unchanged
// 1 = enabled after reminder integration and testing
#define RIA_ENABLE_DEVICE_REMINDERS 1

// Check for due reminders every 5 seconds when idle.
#define RIA_REMINDER_POLL_MS 5000


#include "private/wifi_config.h"
#include "esp_3inch5_lcd_port.h"

#define EXAMPLE_PIN_I2C_SDA GPIO_NUM_8
#define EXAMPLE_PIN_I2C_SCL GPIO_NUM_7

#define EXAMPLE_PIN_BUTTON GPIO_NUM_0

#define EXAMPLE_DISPLAY_ROTATION 90

#if EXAMPLE_DISPLAY_ROTATION == 90 || EXAMPLE_DISPLAY_ROTATION == 270
#define EXAMPLE_LCD_H_RES 480
#define EXAMPLE_LCD_V_RES 320
#else
#define EXAMPLE_LCD_H_RES 320
#define EXAMPLE_LCD_V_RES 480
#endif

#define LCD_BUFFER_SIZE EXAMPLE_LCD_H_RES *EXAMPLE_LCD_V_RES / 8

#define I2C_PORT_NUM 0

static const char *TAG = "lvgl_example";

i2c_master_bus_handle_t i2c_bus_handle;

esp_lcd_panel_io_handle_t io_handle = NULL;
esp_lcd_panel_handle_t panel_handle = NULL;
esp_io_expander_handle_t expander_handle = NULL;
esp_lcd_touch_handle_t touch_handle = NULL;
lv_disp_drv_t disp_drv;

lv_display_t *lvgl_disp = NULL;
lv_indev_t *lvgl_touch_indev = NULL;

bool touch_test_done = false;
// sdmmc_card_t *card = NULL;

void i2c_bus_init(void);
void io_expander_init(void);
void lv_port_init(void);



// RIA_OVERLAPPED_WAV_PLAYBACK_V1
// One speaker worker at a time; no concurrent codec writes.
// The worker owns and frees the WAV buffer.
struct RiaPlaybackJob {
    uint8_t *wav = nullptr;
    size_t pcm_bytes = 0;
    SemaphoreHandle_t done = nullptr;
    bool success = false;
};

static void ria_playback_worker(void *arg)
{
    RiaPlaybackJob *job =
        static_cast<RiaPlaybackJob *>(arg);

    job->success = ria_play_pcm(
        job->wav + 44,
        job->pcm_bytes
    );

    heap_caps_free(job->wav);
    job->wav = nullptr;

    xSemaphoreGive(job->done);
    vTaskDelete(nullptr);
}

static void ria_http_test_task(void *arg)
{
    vTaskDelay(pdMS_TO_TICKS(8000));

    esp_http_client_config_t config = {};
    config.url = "http://192.168.0.104:8040/ping";
    config.timeout_ms = 5000;

    esp_http_client_handle_t client =
        esp_http_client_init(&config);

    if (client == nullptr) {
        ESP_LOGE("RIA_HTTP", "HTTP client init failed");
        vTaskDelete(NULL);
        return;
    }

    esp_err_t err = esp_http_client_perform(client);

    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        ESP_LOGI("RIA_HTTP", "Mac HTTP status: %d", status);
    } else {
        ESP_LOGE("RIA_HTTP", "Request failed: %s",
                 esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    vTaskDelete(NULL);
}


// RIA_VISUAL_STATE_BRIDGE_V1
// Safe to call from the audio task.
// LVGL operations are protected by the port mutex.

// RIA_REMINDER_INTERRUPT_V1
// Read-only atomic state; no LVGL API calls here.
static bool ria_reminder_playback_active = false;

extern "C" bool ria_reminder_stop_playback_requested(void)
{
    return __atomic_load_n(
        &ria_reminder_playback_active, __ATOMIC_ACQUIRE
    ) && ria_reminder_interrupt_pending();
}

static void ria_update_visual_state(RiaVisualState state)
{
    if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
        ria_set_visual_state(state);
        lvgl_port_unlock();
    } else {
        ESP_LOGW(
            "RIA_UI",
            "Visual-state update skipped: LVGL busy"
        );
    }
}

// RIA_AUDIO_MEMORY_DIAGNOSTIC_V1
static void ria_log_audio_memory(void)
{
    ESP_LOGI(
        "RIA_MEMORY",
        "PSRAM free: %u bytes, largest block: %u bytes",
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)
    );

    ESP_LOGI(
        "RIA_MEMORY",
        "Internal RAM free: %u bytes, largest block: %u bytes",
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL)
    );
}

// RIA_RING_SELF_TEST_INTEGRATION_V1
static bool ria_ring_test_completed = false;

static void ria_audio_test_task(void *arg)
{
    TickType_t last_reminder_poll = xTaskGetTickCount();

    // RIA_ORBIT_INFOBAR_V1
    TickType_t last_info_poll =
        xTaskGetTickCount() - pdMS_TO_TICKS(60000);
    // RIA_ORBIT_UPCOMING_V1
    TickType_t last_upcoming_poll =
        xTaskGetTickCount() - pdMS_TO_TICKS(60000);


    while (true) {
        if (!ria_ring_test_completed) {
            ria_ring_test_completed = true;

            bool passed = ria_pcm_ring_self_test();

            // RIA_RING_CONCURRENCY_INTEGRATION_V1
            bool concurrent_passed =
                ria_pcm_ring_concurrency_test();

            ESP_LOGI(
                "RIA_RING_TEST",
                "Concurrency self-test: %s",
                concurrent_passed ? "PASS" : "FAIL"
            );

            ESP_LOGI(
                "RIA_RING_TEST",
                "Startup self-test: %s",
                passed ? "PASS" : "FAIL"
            );
        }

        static bool memory_logged = false;

        if (!memory_logged) {
            ria_log_audio_memory();
            memory_logged = true;
        }


        // RIA_ORBIT_UPCOMING_V1
        // Read-only display refresh. Never claim or acknowledge here.
        // RIA_ORBIT_UPCOMING_WIFI_FIX_V2
        // Do not refresh until the ESP32 has a valid IPv4 address.
        esp_netif_t *ria_sta = esp_netif_get_handle_from_ifkey(
            "WIFI_STA_DEF"
        );
        esp_netif_ip_info_t ria_ip = {};

        bool ria_wifi_ready =
            ria_sta != nullptr &&
            esp_netif_get_ip_info(ria_sta, &ria_ip) == ESP_OK &&
            ria_ip.ip.addr != 0;

        // RIA_MEMORY_TRANSPORT_A328 polling hook
#if RIA_ENABLE_MEMORY_APPROVAL_UI
        ria_memory_transport_tick(
            ria_wifi_ready &&
            !ria_mic_requests &&
            !__atomic_load_n(
                &ria_reminder_action_enabled,
                __ATOMIC_ACQUIRE
            )
        );
#endif

        if (ria_wifi_ready &&
            !ria_mic_requests &&
            (xTaskGetTickCount() - last_upcoming_poll) >=
                pdMS_TO_TICKS(60000)) {

            last_upcoming_poll = xTaskGetTickCount();

            char titles[2][48] = {};
            char times[2][16] = {};

            if (ria_fetch_upcoming(titles, times)) {
                if (lvgl_port_lock(1000)) {
                    // RIA_REMINDER_CONTEXT_V2
                        ria_title_case_display(titles[0]);
                        ria_title_case_display(titles[1]);
                        ria_upcoming_update(titles, times);
                    lvgl_port_unlock();
                }
            } else {
                ESP_LOGW(
                    "RIA_UPCOMING",
                    "Refresh unavailable; keeping previous display"
                );
            }
        }


        // RIA_ORBIT_INFOBAR_V1
        // Update time/date/weather only when idle and Wi-Fi is ready.
        {
            esp_netif_t *info_sta =
                esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
            esp_netif_ip_info_t info_ip = {};

            bool info_wifi_ready =
                info_sta != nullptr &&
                esp_netif_get_ip_info(info_sta, &info_ip) == ESP_OK &&
                info_ip.ip.addr != 0;

            if (info_wifi_ready &&
                !ria_mic_requests &&
                (xTaskGetTickCount() - last_info_poll) >=
                    pdMS_TO_TICKS(60000)) {

                last_info_poll = xTaskGetTickCount();

                char clock_text[24] = {};
                char date_text[40] = {};
                char weather_text[48] = {};

                if (ria_fetch_device_info(
                    clock_text, date_text, weather_text
                )) {
                    if (lvgl_port_lock(1000)) {
                        ria_home_info_update(
                            clock_text, date_text, weather_text
                        );
                        lvgl_port_unlock();
                    }
                    ESP_LOGI(
                        "RIA_INFO", "Clock and weather updated"
                    );
                } else {
                    ESP_LOGW(
                        "RIA_INFO", "Info bar refresh unavailable"
                    );
                }
            }
        }

#if RIA_ENABLE_DEVICE_REMINDERS
        // RIA_REMINDER_POLL_INTEGRATION_V1
        // The audio task owns microphone and speaker access.
        // Never claim reminders while a MIC request is pending.
        if (!ria_mic_requests &&
            (xTaskGetTickCount() - last_reminder_poll) >=
                pdMS_TO_TICKS(RIA_REMINDER_POLL_MS)) {

            last_reminder_poll = xTaskGetTickCount();

            RiaReminder reminder = {};

            if (ria_claim_reminder(&reminder)) {
                ESP_LOGI(
                    "RIA_REMINDER",
                    "Announcing reminder ID=%d",
                    reminder.id
                );

                char announcement[256] = {};
                snprintf(
                    announcement,
                    sizeof(announcement),
                    "Reminder. %s",
                    reminder.title
                );

                // RIA_REMINDER_DISPLAY_INTEGRATION_V1
                // Show the reminder under the LVGL mutex.
                if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
                    ria_reminder_overlay_show(reminder.title);
                    lvgl_port_unlock();
                } else {
                    ESP_LOGW(
                        "RIA_REMINDER",
                        "Display lock unavailable"
                    );
                }

                // RIA_REMINDER_FULL_WAV_V1
                // Use the proven full-WAV playback path.
                // The audio task owns reminder announcements.
                bool played = false;
                size_t reminder_pcm_bytes = 0;

                uint8_t *reminder_wav = ria_download_speech(
                    announcement,
                    &reminder_pcm_bytes
                );

                if (reminder_wav != nullptr &&
                    reminder_pcm_bytes > 0) {

                    ESP_LOGI(
                        "RIA_REMINDER",
                        "Playing WAV announcement: %u PCM bytes",
                        (unsigned)reminder_pcm_bytes
                    );

                    // RIA_REMINDER_INTERRUPT_V1
                    __atomic_store_n(
                        &ria_reminder_playback_active,
                        true, __ATOMIC_RELEASE
                    );

                    if (!ria_reminder_interrupt_pending()) {
                        played = ria_play_pcm(
                            reminder_wav + 44,
                            reminder_pcm_bytes
                        );
                    }

                    __atomic_store_n(
                        &ria_reminder_playback_active,
                        false, __ATOMIC_RELEASE
                    );
                } else {
                    ESP_LOGE(
                        "RIA_REMINDER",
                        "WAV announcement download failed"
                    );
                }

                if (reminder_wav != nullptr) {
                    heap_caps_free(reminder_wav);
                    reminder_wav = nullptr;
                }

                ESP_LOGI(
                    "RIA_REMINDER",
                    "Full-WAV announcement result: %s",
                    played ? "PASS" : "FAIL"
                );


                // RIA_INTERACTIVE_REMINDERS_V1
                // Delivery acknowledgement is NOT task completion.

                if (played ||
                    ria_reminder_interrupt_pending()) {
                    if (played) {
                    bool acknowledged =
                        ria_acknowledge_reminder(reminder);

                    ESP_LOGI(
                        "RIA_REMINDER",
                        "Acknowledgement: %s",
                        acknowledged ? "PASS" : "FAIL"
                    );

                    } else {
                        ESP_LOGI(
                            "RIA_REMINDER",
                            "Announcement interrupted for touch action"
                        );
                    }

                    if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
                        ria_reminder_overlay_ready();
                        lvgl_port_unlock();
                    }


                    // RIA_REMINDER_VOICE_ACTION_V1
                    // Announcements have finished: microphone is free.
                    // A touchscreen action selected during playback wins.
                    int ria_voice_seconds = 0;

                    if (__atomic_load_n(
                        &ria_reminder_action_requested,
                        __ATOMIC_ACQUIRE) == 0) {

                        if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
                            if (ria_reminder_instruction) {
                                lv_label_set_text(
                                    ria_reminder_instruction,
                                    "Listening for your response..."
                                );
                            }
                            lvgl_port_unlock();
                        }

                        ESP_LOGI(
                            "RIA_REMINDER_VOICE",
                            "Listening for Done, Snooze or Skip"
                        );

                        size_t response_pcm_size = 0;
                        uint8_t *response_pcm =
                            ria_capture_audio(&response_pcm_size);

                        char response_transcript[512] = {};
                        esp_err_t stt_result = ESP_FAIL;

                        if (response_pcm &&
                            response_pcm_size > 0) {
                            stt_result = ria_upload_pcm(
                                response_pcm,
                                response_pcm_size,
                                response_transcript,
                                sizeof(response_transcript)
                            );
                        }

                        if (response_pcm)
                            heap_caps_free(response_pcm);

                        int voice_action = 0;

                        if (stt_result == ESP_OK &&
                            response_transcript[0]) {

                            ESP_LOGI(
                                "RIA_REMINDER_VOICE",
                                "Recognized: %s",
                                response_transcript
                            );

                            char clean[512] = {};
                            size_t length =
                                strlen(response_transcript);

                            if (length >= sizeof(clean))
                                length = sizeof(clean) - 1;

                            for (size_t i = 0; i < length; ++i) {
                                char ch = response_transcript[i];

                                if (ch >= 'A' && ch <= 'Z')
                                    ch = ch - 'A' + 'a';

                                if ((ch >= 'a' && ch <= 'z') ||
                                    (ch >= '0' && ch <= '9') ||
                                    ch == ' ')
                                    clean[i] = ch;
                                else
                                    clean[i] = ' ';
                            }

                            // Ignore leading wake/name phrases.
                            const char *command = clean;

                            while (*command == ' ')
                                ++command;

                            if (strncmp(command, "hey ria ", 8) == 0)
                                command += 8;
                            else if (strncmp(command, "ria ", 4) == 0)
                                command += 4;
                            else if (strncmp(command, "rhea ", 5) == 0)
                                command += 5;

                            while (*command == ' ')
                                ++command;

                            // Parse only explicit supported commands.
                            if (
                                strcmp(command, "done") == 0 ||
                                strcmp(command, "done ") == 0 ||
                                strncmp(command, "mark it done", 12) == 0 ||
                                strncmp(command, "i did it", 8) == 0 ||
                                strncmp(command, "completed", 9) == 0
                            ) {
                                voice_action = 1;

                            } else if (
                                strncmp(command, "skip", 4) == 0 ||
                                strncmp(command, "dismiss", 7) == 0
                            ) {
                                voice_action = 3;

                            } else if (
                                strncmp(command, "snooze", 6) == 0 ||
                                strncmp(command, "remind me in ", 13) == 0
                            ) {
                                const char *duration =
                                    strncmp(command, "snooze", 6) == 0
                                        ? command + 6
                                        : command + 13;

                                while (*duration == ' ')
                                    ++duration;

                                if (strncmp(duration, "for ", 4) == 0)
                                    duration += 4;

                                while (*duration == ' ')
                                    ++duration;

                                // Bare "snooze" means five minutes.
                                if (*duration == '\0') {
                                    voice_action = 2;
                                    ria_voice_seconds = 300;
                                } else {
                                    int amount = 0;
                                    char unit[24] = {};

                                    if (sscanf(
                                        duration,
                                        "%d %23s",
                                        &amount, unit
                                    ) == 2 && amount > 0) {

                                        int multiplier = 0;

                                        if (strncmp(unit, "sec", 3) == 0)
                                            multiplier = 1;
                                        else if (
                                            strncmp(unit, "min", 3) == 0
                                        )
                                            multiplier = 60;
                                        else if (
                                            strncmp(unit, "hour", 4) == 0 ||
                                            strcmp(unit, "hr") == 0 ||
                                            strcmp(unit, "hrs") == 0
                                        )
                                            multiplier = 3600;

                                        if (multiplier > 0 &&
                                            amount <=
                                                31536000 / multiplier) {
                                            ria_voice_seconds =
                                                amount * multiplier;
                                            voice_action = 2;
                                        }
                                    }
                                }
                            }
                        }


                        // RIA_REMINDER_CONTEXT_V2
                        // In a reminder response, a bare duration
                        // such as "30 seconds" means snooze.
                        if (voice_action == 0) {
                            // RIA_REMINDER_COMMAND_SCOPE_FIX_V1
                            // 'command' was scoped to the STT parsing block.
                            // Rebuild the normalized phrase from the
                            // transcript, which remains in scope here.
                            char standalone_command[512] = {};
                            size_t standalone_length =
                                strlen(response_transcript);

                            if (standalone_length >= sizeof(standalone_command))
                                standalone_length =
                                    sizeof(standalone_command) - 1;

                            for (size_t i = 0; i < standalone_length; ++i) {
                                char ch = response_transcript[i];

                                if (ch >= 'A' && ch <= 'Z')
                                    ch = (char)(ch - 'A' + 'a');

                                if ((ch >= 'a' && ch <= 'z') ||
                                    (ch >= '0' && ch <= '9') ||
                                    ch == ' ')
                                    standalone_command[i] = ch;
                                else
                                    standalone_command[i] = ' ';
                            }

                            const char *short_command = standalone_command;

                            while (*short_command == ' ')
                                ++short_command;

                            if (strncmp(
                                short_command, "for ", 4
                            ) == 0) {
                                short_command += 4;
                            }

                            int amount = 0;
                            char unit[24] = {};
                            char extra = '\0';

                            // Reject ambiguous extra words.
                            int matched = sscanf(
                                short_command,
                                "%d %23s %c",
                                &amount, unit, &extra
                            );

                            if (matched == 2 && amount > 0) {
                                int multiplier = 0;

                                if (strcmp(unit, "s") == 0 ||
                                    strncmp(unit, "sec", 3) == 0)
                                    multiplier = 1;

                                else if (strcmp(unit, "m") == 0 ||
                                         strncmp(unit, "min", 3) == 0)
                                    multiplier = 60;

                                else if (strcmp(unit, "h") == 0 ||
                                         strcmp(unit, "hr") == 0 ||
                                         strcmp(unit, "hrs") == 0 ||
                                         strncmp(unit, "hour", 4) == 0)
                                    multiplier = 3600;

                                if (multiplier > 0 &&
                                    amount <= 31536000 / multiplier) {
                                    ria_voice_seconds =
                                        amount * multiplier;
                                    voice_action = 2;
                                }
                            }
                        }

                        if (voice_action != 0) {
                            // Do not overwrite a touch action.
                            int expected = 0;
                            bool stored =
                                __atomic_compare_exchange_n(
                                    &ria_reminder_action_requested,
                                    &expected,
                                    voice_action,
                                    false,
                                    __ATOMIC_ACQ_REL,
                                    __ATOMIC_ACQUIRE
                                );

                            if (!stored)
                                ria_voice_seconds = 0;

                            ESP_LOGI(
                                "RIA_REMINDER_VOICE",
                                "Action=%d seconds=%d queued=%d",
                                voice_action,
                                ria_voice_seconds,
                                stored ? 1 : 0
                            );
                        } else {
                            ESP_LOGI(
                                "RIA_REMINDER_VOICE",
                                "No supported voice action recognized"
                            );
                        }

                        if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
                            if (ria_reminder_instruction) {
                                lv_label_set_text(
                                    ria_reminder_instruction,
                                    "Touch Done, Snooze or Skip"
                                );
                            }
                            lvgl_port_unlock();
                        }
                    }

                    const TickType_t response_start =
                        xTaskGetTickCount();

                    bool action_completed = false;

                    while (
                        (xTaskGetTickCount() - response_start) <
                        pdMS_TO_TICKS(20000)
                    ) {
                        const int action = __atomic_exchange_n(
                            &ria_reminder_action_requested,
                            0, __ATOMIC_ACQ_REL
                        );

                        if (action >= 1 && action <= 3) {
                            if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
                                ria_reminder_overlay_saving();
                                lvgl_port_unlock();
                            }

                            bool accepted =
                                ria_send_reminder_user_action(
                                    reminder, action,
                                    action == 2 ? ria_voice_seconds : 0
                                );

                            ESP_LOGI(
                                "RIA_REMINDER",
                                "User action %d: %s",
                                action,
                                accepted ? "PASS" : "FAIL"
                            );

                            if (accepted) {
                                action_completed = true;
                                break;
                            }

                            if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
                                ria_reminder_overlay_action_failed();
                                lvgl_port_unlock();
                            }
                        }

                        vTaskDelay(pdMS_TO_TICKS(50));
                    }

                    ESP_LOGI(
                        "RIA_REMINDER",
                        "Response window: %s",
                        action_completed ? "ACTION SAVED" : "NO ACTION"
                    );

                } else {
                    ESP_LOGW(
                        "RIA_REMINDER",
                        "Playback failed; reminder not acknowledged"
                    );
                }

                __atomic_store_n(
                    &ria_reminder_action_enabled,
                    false, __ATOMIC_RELEASE
                );

                // RIA_REMINDER_IMMEDIATE_CARD_SYNC_V1
                // Fetch fresh reminder data before uncovering home.
                // Never keep a completed reminder on the card.
                char updated_titles[2][48] = {};
                char updated_times[2][16] = {};

                bool synced = ria_fetch_upcoming(
                    updated_titles, updated_times
                );

                if (lvgl_port_lock(pdMS_TO_TICKS(1000))) {
                    if (synced) {
                        ria_title_case_display(updated_titles[0]);
                        ria_title_case_display(updated_titles[1]);

                        ria_upcoming_update(
                            updated_titles, updated_times
                        );
                    }

                    ria_reminder_overlay_hide();
                    lvgl_port_unlock();
                }

                if (synced) {
                    last_upcoming_poll = xTaskGetTickCount();

                    ESP_LOGI(
                        "RIA_UPCOMING",
                        "Reminder card synchronized after action"
                    );
                } else {
                    // Retry promptly in the ordinary idle loop.
                    last_upcoming_poll =
                        xTaskGetTickCount() -
                        pdMS_TO_TICKS(60000);

                    ESP_LOGW(
                        "RIA_UPCOMING",
                        "Immediate sync unavailable; retry scheduled"
                    );
                }

            }
        }
#endif

        if (ria_mic_requests) {
            ria_mic_requests = false;
            // RIA_AUDIO_VISUAL_FLOW_V1
            ria_update_visual_state(RIA_STATE_LISTENING);

            ESP_LOGI("RIA_AUDIO",
                     "MIC tapped: recording for Whisper");

            size_t pcm_size = 0;
            uint8_t *pcm = ria_capture_audio(&pcm_size);

            if (pcm != nullptr && pcm_size > 0) {
                ESP_LOGI("RIA_AUDIO",
                         "Uploading %u PCM bytes",
                         (unsigned)pcm_size);

                char transcript[1024] = {};

                esp_err_t result = ria_upload_pcm(
                    pcm,
                    pcm_size,
                    transcript,
                    sizeof(transcript)
                );

                ria_update_visual_state(RIA_STATE_THINKING);

                // Release the microphone buffer before LLM processing.
                heap_caps_free(pcm);

                ESP_LOGI("RIA_AUDIO",
                         "Transcription result: %s",
                         esp_err_to_name(result));

                if (result == ESP_OK && transcript[0]) {
                    ESP_LOGI(
                        "RIA_AUDIO",
                        "Recognized: %s",
                        transcript
                    );

                    char reply[4096] = {};

                    esp_err_t llm_result =
                        ria_send_conversation(
                            transcript,
                            reply,
                            sizeof(reply)
                        );

                    ESP_LOGI(
                        "RIA_AUDIO",
                        "Conversation result: %s",
                        esp_err_to_name(llm_result)
                    );

                    if (llm_result == ESP_OK && reply[0]) {
                        // RIA_FULL_REPLY_CHUNKS_V1
                        // Speak the complete available AI reply using bounded segments.
                        // Preserve the proven full-WAV download and PCM playback path.
                        const size_t total = strlen(reply);
                        // RIA_A3433_FULL_REPLY
                        // Full-reply TTS for messages up to 500 bytes.
                        // Preserve bounded segmentation for longer replies.
#if RIA_USE_SENTENCE_STREAM_AUDIO
                        const size_t max_segment = 500;
#else
                        const size_t max_segment = 140;
#endif

                        size_t offset = 0;
                        size_t segments = 0;
                        bool all_played = true;

#if !RIA_USE_STREAMING_AUDIO && !RIA_USE_SENTENCE_STREAM_AUDIO
RiaPlaybackJob playback_job = {};
SemaphoreHandle_t playback_done =
    xSemaphoreCreateBinary();

bool playback_pending = false;
size_t pending_segment = 0;
size_t played_offset = 0;
size_t pending_end_offset = 0;
#endif

                        ria_update_visual_state(RIA_STATE_SPEAKING);

                        while (offset < total) {
                            // Skip whitespace between segments.
                            while (offset < total &&
                                   (reply[offset] == ' ' ||
                                    reply[offset] == '\n' ||
                                    reply[offset] == '\r' ||
                                    reply[offset] == '\t')) {
                                ++offset;
                            }

                            if (offset >= total)
                                break;

                            size_t end = offset + max_segment;
                            if (end > total)
                                end = total;

                            // Never end a segment inside a UTF-8 continuation byte.
                            if (end < total) {
                                while (end > offset &&
                                       (((unsigned char)reply[end] & 0xC0) == 0x80)) {
                                    --end;
                                }
                            }

                            if (end <= offset) {
                                ESP_LOGE("RIA_AUDIO", "Invalid UTF-8 segment boundary");
                                all_played = false;
                                break;
                            }

                            size_t chosen = end;

                            if (end < total) {
                                const size_t min_break =
                                    offset + (end - offset) / 2;

                                bool found_sentence = false;

                                // Prefer a completed sentence when possible.
                                for (size_t j = end; j > min_break; --j) {
                                    char previous = reply[j - 1];
                                    char next = reply[j];

                                    if ((previous == '.' ||
                                         previous == '!' ||
                                         previous == '?') &&
                                        (next == ' ' ||
                                         next == '\n' ||
                                         next == '\r' ||
                                         next == '\t')) {
                                        chosen = j;
                                        found_sentence = true;
                                        break;
                                    }
                                }

                                // Otherwise stop at a word boundary.
                                if (!found_sentence) {
                                    for (size_t j = end; j > min_break; --j) {
                                        if (reply[j] == ' ' ||
                                            reply[j] == '\n' ||
                                            reply[j] == '\r' ||
                                            reply[j] == '\t') {
                                            chosen = j;
                                            break;
                                        }
                                    }
                                }
                            }

                            if (chosen <= offset) {
                                all_played = false;
                                ESP_LOGE("RIA_AUDIO", "Speech segmentation stalled");
                                break;
                            }

                            #if RIA_USE_SENTENCE_STREAM_AUDIO
                            char speech_text[501] = {};
#else
                            char speech_text[141] = {};
#endif
                            const size_t length = chosen - offset;

                            memcpy(speech_text, reply + offset, length);
                            speech_text[length] = '\0';

                            offset = chosen;
                            ++segments;

                            ESP_LOGI(
                                "RIA_AUDIO",
                                "Speech segment %u: %u bytes, progress %u/%u",
                                (unsigned)segments,
                                (unsigned)length,
                                (unsigned)offset,
                                (unsigned)total
                            );

                            ESP_LOGI(
                                "RIA_AUDIO",
                                "Generating voice: %s",
                                speech_text
                            );

                        #if RIA_USE_SENTENCE_STREAM_AUDIO
                            bool played = ria_sentence_stream_speech(speech_text, "neutral");

                            ESP_LOGI(
                                "RIA_AUDIO",
                                "Sentence stream result: %s",
                                played ? "PASS" : "FAIL"
                            );

                            if (!played) {
                                all_played = false;
                                break;
                            }
#elif RIA_USE_STREAMING_AUDIO
                            bool played = ria_stream_speech(speech_text);

                            ESP_LOGI(
                                "RIA_AUDIO",
                                "Streaming result: %s",
                                played ? "PASS" : "FAIL"
                            );

                            if (!played) {
                                all_played = false;
                                break;
                            }
                        #else
    size_t pcm_bytes = 0;
    uint8_t *wav = ria_download_speech(
        speech_text, &pcm_bytes
    );

    // The previous segment may still be playing while
    // this WAV downloads. Join it before starting another.
    if (playback_pending) {
        xSemaphoreTake(
            playback_done, portMAX_DELAY
        );

        playback_pending = false;

        ESP_LOGI(
            "RIA_AUDIO",
            "Speaker segment %u result: %s",
            (unsigned)pending_segment,
            playback_job.success ? "PASS" : "FAIL"
        );

        if (playback_job.success)
            played_offset = pending_end_offset;

        if (!playback_job.success)
            all_played = false;
    }

    if (wav == nullptr || pcm_bytes == 0 ||
        !all_played) {

        if (wav != nullptr)
            heap_caps_free(wav);

        ESP_LOGE(
            "RIA_AUDIO",
            "Segment %u unavailable or prior playback failed",
            (unsigned)segments
        );

        all_played = false;
        break;
    }

    ESP_LOGI(
        "RIA_AUDIO",
        "Playing segment %u: %u PCM bytes",
        (unsigned)segments,
        (unsigned)pcm_bytes
    );

    if (playback_done != nullptr) {
        playback_job.wav = wav;
        playback_job.pcm_bytes = pcm_bytes;
        playback_job.done = playback_done;
        playback_job.success = false;

        BaseType_t started = xTaskCreate(
            ria_playback_worker,
            "ria_pcm_play",
            8192,
            &playback_job,
            5,
            nullptr
        );

        if (started == pdPASS) {
            playback_pending = true;
            pending_segment = segments;
            pending_end_offset = offset;
            wav = nullptr;
        }
    }

    // Safe fallback if no semaphore or worker available.
    if (wav != nullptr) {
        bool played = ria_play_pcm(
            wav + 44, pcm_bytes
        );

        heap_caps_free(wav);

        ESP_LOGI(
            "RIA_AUDIO",
            "Speaker segment %u result: %s",
            (unsigned)segments,
            played ? "PASS" : "FAIL"
        );

        if (!played) {
            all_played = false;
            break;
        }

        played_offset = offset;
    }
#endif
                        }

                        #if !RIA_USE_STREAMING_AUDIO && !RIA_USE_SENTENCE_STREAM_AUDIO
                        if (playback_pending) {
                            xSemaphoreTake(playback_done, portMAX_DELAY);
                            playback_pending = false;

                            ESP_LOGI(
                                "RIA_AUDIO",
                                "Speaker segment %u result: %s",
                                (unsigned)pending_segment,
                                playback_job.success ? "PASS" : "FAIL"
                            );

                            if (playback_job.success)
                                played_offset = pending_end_offset;
                            else
                                all_played = false;
                        }

                        if (playback_done != nullptr)
                            vSemaphoreDelete(playback_done);
                        #endif
                        ESP_LOGI(
                            "RIA_AUDIO",
                            "Full reply playback: %s, segments=%u, bytes=%u/%u",
                            all_played && offset >= total
#if !RIA_USE_STREAMING_AUDIO && !RIA_USE_SENTENCE_STREAM_AUDIO
                            && played_offset >= total
#endif
                            ? "PASS" : "FAIL",
                            (unsigned)segments,
                            (unsigned)offset,
                            (unsigned)total
                        );

                    ESP_LOGI(
                        "RIA_MEMORY",
                        "Audio task minimum free stack: %u bytes",
                        (unsigned)uxTaskGetStackHighWaterMark(NULL)
                    );
                    }
                } else {
                    ESP_LOGW(
                        "RIA_AUDIO",
                        "No usable speech recognized"
                    );
                }
            } else {
                // RIA_CAPTURE_NULL_LOG_V1
            // NULL may mean silence timeout or capture failure.
            // The capture routine logs the specific reason.
            ESP_LOGI(
                "RIA_AUDIO",
                "No audio captured; check RIA_VAD for reason"
            );
            }

            // RIA_REMINDER_REFRESH_TOUCH_DIAG_V1
            // Refresh reminder cards after voice conversations,
            // including successful reminder creation.
            last_upcoming_poll =
                xTaskGetTickCount() - pdMS_TO_TICKS(60000);

            ESP_LOGI(
                "RIA_UPCOMING",
                "Immediate refresh requested after conversation"
            );

            ria_update_visual_state(RIA_STATE_IDLE);
        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

extern "C" void app_main(void)
{
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND)
    {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    i2c_bus_init();
    io_expander_init();
    esp_3inch5_display_port_init(&io_handle, &panel_handle, LCD_BUFFER_SIZE);
    esp_3inch5_touch_port_init(&touch_handle, i2c_bus_handle, EXAMPLE_LCD_H_RES, EXAMPLE_LCD_V_RES, EXAMPLE_DISPLAY_ROTATION);
    esp_axp2101_port_init(i2c_bus_handle);
    vTaskDelay(pdMS_TO_TICKS(100));
    esp_es8311_port_init(i2c_bus_handle);

    xTaskCreate(
        ria_audio_test_task,
        "ria_audio",
        24576,
        NULL,
        5,
        NULL
    );
    // esp_qmi8658_port_init(i2c_bus_handle);
    // esp_pcf85063_port_init(i2c_bus_handle);
    // esp_sdcard_port_init();
    // esp_camera_port_init(I2C_PORT_NUM);
    esp_wifi_port_init(RIA_WIFI_SSID, RIA_WIFI_PASSWORD);
    // Legacy HTTP ping test disabled.
    // Audio now uploads through the authenticated bridge on port 8041.

    esp_3inch5_brightness_port_init();
    esp_3inch5_brightness_port_set(80);
    lv_port_init();
    
    if (lvgl_port_lock(0))
    {
        // lv_demo_benchmark();
        // lv_demo_music();
        ria_home_create();
        // lvgl_ui_init();
        lvgl_port_unlock();
    }
}

void i2c_bus_init(void)
{
    i2c_master_bus_config_t i2c_mst_config = {};
    i2c_mst_config.clk_source = I2C_CLK_SRC_DEFAULT;
    i2c_mst_config.i2c_port = (i2c_port_num_t)I2C_PORT_NUM;
    i2c_mst_config.scl_io_num = EXAMPLE_PIN_I2C_SCL;
    i2c_mst_config.sda_io_num = EXAMPLE_PIN_I2C_SDA;
    i2c_mst_config.glitch_ignore_cnt = 7;
    i2c_mst_config.flags.enable_internal_pullup = 1;

    ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config, &i2c_bus_handle));
}

void io_expander_init(void)
{
    ESP_ERROR_CHECK(esp_io_expander_new_i2c_tca9554(i2c_bus_handle, ESP_IO_EXPANDER_I2C_TCA9554_ADDRESS_000, &expander_handle));
    ESP_ERROR_CHECK(esp_io_expander_set_dir(expander_handle,  IO_EXPANDER_PIN_NUM_1, IO_EXPANDER_OUTPUT));
    ESP_ERROR_CHECK(esp_io_expander_set_level(expander_handle, IO_EXPANDER_PIN_NUM_1, 0));
    vTaskDelay(pdMS_TO_TICKS(100));
    ESP_ERROR_CHECK(esp_io_expander_set_level(expander_handle, IO_EXPANDER_PIN_NUM_1, 1));
    vTaskDelay(pdMS_TO_TICKS(100));
}

void lv_port_init(void)
{
    lvgl_port_cfg_t port_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    lvgl_port_init(&port_cfg);
    ESP_LOGI(TAG, "Adding LCD screen");
    lvgl_port_display_cfg_t display_cfg = {
        .io_handle = io_handle,
        .panel_handle = panel_handle,
        .control_handle = NULL,
        .buffer_size = LCD_BUFFER_SIZE,
        .double_buffer = true,
        .trans_size = 0,
        .hres = EXAMPLE_LCD_H_RES,
        .vres = EXAMPLE_LCD_V_RES,
        .monochrome = false,
        .rotation = {
            .swap_xy = 0,
            .mirror_x = 1,
            .mirror_y = 0,
        },
        .flags = {
            .buff_dma = 0,
            .buff_spiram = 1,
            .sw_rotate = 1,
            .full_refresh = 0,
            .direct_mode = 0,
        },
    };

#if EXAMPLE_DISPLAY_ROTATION == 90
    display_cfg.rotation.swap_xy = 1;
    display_cfg.rotation.mirror_x = 1;
    display_cfg.rotation.mirror_y = 1;
#elif EXAMPLE_DISPLAY_ROTATION == 180
    display_cfg.rotation.swap_xy = 0;
    display_cfg.rotation.mirror_x = 0;
    display_cfg.rotation.mirror_y = 1;

#elif EXAMPLE_DISPLAY_ROTATION == 270
    display_cfg.rotation.swap_xy = 1;
    display_cfg.rotation.mirror_x = 0;
    display_cfg.rotation.mirror_y = 0;
#endif

    lvgl_disp = lvgl_port_add_disp(&display_cfg);
    const lvgl_port_touch_cfg_t touch_cfg = {
        .disp = lvgl_disp,
        .handle = touch_handle,
    };
    lvgl_touch_indev = lvgl_port_add_touch(&touch_cfg);
}