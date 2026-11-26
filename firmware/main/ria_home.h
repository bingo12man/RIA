#include "esp_log.h"
// RIA_MINIMAL_HOME_V1
// RIA_ACCESSIBILITY_ESSENTIALS_V1
#pragma once
#include <atomic>
#include "lvgl.h"
#include "ria_lotus_mouth.h"
#include <cstring>
#include "ria_lotus_states.h"
LV_IMG_DECLARE(ria_mascot);


static lv_obj_t *ria_status = nullptr;
static volatile bool ria_mic_requests = false;

// RIA_VISUAL_STATE_V1
// Caller must hold lvgl_port_lock().
enum RiaVisualState {
    RIA_STATE_IDLE,
    RIA_STATE_LISTENING,
    RIA_STATE_THINKING,
    RIA_STATE_SPEAKING
};


// RIA_EXPRESSIVE_MASCOT_V1
// All functions below must run while LVGL is locked.
static lv_obj_t *ria_mascot_object = nullptr;
static RiaVisualState ria_current_visual_state = RIA_STATE_IDLE;

static void ria_mascot_float_cb(void *obj, int32_t y);


// RIA_LOTUS_STATE_IMAGES_V1
static const void *ria_mascot_for_state(RiaVisualState state)
{
    switch (state) {
        case RIA_STATE_LISTENING:
            return &ria_lotus_listening;
        case RIA_STATE_THINKING:
            return &ria_lotus_thinking;
        case RIA_STATE_SPEAKING:
            return &ria_lotus_speaking;
        case RIA_STATE_IDLE:
        default:
            return &ria_lotus_idle;
    }
}


// RIA_REAL_MOUTH_SYNC_V2
extern std::atomic<uint8_t> ria_mouth_level;
extern std::atomic<bool> ria_audio_playing;

// RIA_FOCUS_LIPSYNC_V3
static lv_obj_t *ria_focus_mascot = nullptr;

static void ria_real_mouth_timer(lv_timer_t *timer)
{
    (void)timer;
    static int previous = -1;

    if (!ria_mascot_object ||
        ria_current_visual_state != RIA_STATE_SPEAKING ||
        !ria_audio_playing.load(std::memory_order_relaxed)) {
        previous = -1;
        return;
    }

    int level = ria_mouth_level.load(
        std::memory_order_relaxed
    );

    if (level > 2)
        level = 2;

    if (level == previous)
        return;

    const void *image = &ria_lotus_mouth_closed;

    if (level == 1)
        image = &ria_lotus_mouth_half;
    else if (level == 2)
        image = &ria_lotus_mouth_open;

    // Update the visible focus mascot while speaking.
    // Keep the homepage mascot synchronized underneath.
    lv_img_set_src(ria_mascot_object, image);

    if (ria_focus_mascot) {
        lv_img_set_src(ria_focus_mascot, image);
    }

    previous = level;
}

static void ria_mascot_apply_animation(RiaVisualState state)
{
    if (ria_mascot_object == nullptr)
        return;

    int32_t start_y = 58;
    int32_t end_y = 64;
    uint32_t duration_ms = 1900;

    switch (state) {
        case RIA_STATE_LISTENING:
            end_y = 69;
            duration_ms = 700;
            break;

        case RIA_STATE_THINKING:
            end_y = 62;
            duration_ms = 2400;
            break;

        case RIA_STATE_SPEAKING:
            end_y = 67;
            duration_ms = 900;
            break;

        case RIA_STATE_IDLE:
        default:
            end_y = 64;
            duration_ms = 1900;
            break;
    }

    lv_anim_del(
        ria_mascot_object,
        ria_mascot_float_cb
    );

    lv_obj_set_y(ria_mascot_object, start_y);

    lv_anim_t animation;
    lv_anim_init(&animation);
    lv_anim_set_var(&animation, ria_mascot_object);
    lv_anim_set_exec_cb(
        &animation,
        ria_mascot_float_cb
    );
    lv_anim_set_values(
        &animation,
        start_y,
        end_y
    );
    lv_anim_set_time(
        &animation,
        duration_ms
    );
    lv_anim_set_playback_time(
        &animation,
        duration_ms
    );
    lv_anim_set_repeat_count(
        &animation,
        LV_ANIM_REPEAT_INFINITE
    );
    lv_anim_start(&animation);
}

// RIA_ACTIVITY_STRIP_DECLARATION_FIX
static lv_obj_t *ria_activity_strip = nullptr;


// RIA_ORBIT_FOCUS_MODE_V1
static lv_obj_t *ria_focus_overlay = nullptr;

static lv_obj_t *ria_focus_label = nullptr;

static void ria_set_visual_state(RiaVisualState state)
{
    if (ria_status == nullptr)
        return;

    const char *message = "RIA is ready";

    switch (state) {
        case RIA_STATE_LISTENING:
            message = "Listening...";
            break;

        case RIA_STATE_THINKING:
            message = "Thinking...";
            break;

        case RIA_STATE_SPEAKING:
            message = "Speaking...";
            break;

        case RIA_STATE_IDLE:
        default:
            message = "RIA is ready";
            break;
    }

    lv_label_set_text(ria_status, message);

    if (state == RIA_STATE_IDLE) {
        lv_obj_add_flag(
            ria_status, LV_OBJ_FLAG_HIDDEN);
        if (ria_activity_strip)
            lv_obj_add_flag(
                ria_activity_strip, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_clear_flag(
            ria_status, LV_OBJ_FLAG_HIDDEN);
        if (ria_activity_strip)
            lv_obj_clear_flag(
                ria_activity_strip, LV_OBJ_FLAG_HIDDEN);
    }

    if (ria_current_visual_state != state) {
        ria_current_visual_state = state;

        if (ria_mascot_object != nullptr) {
            lv_img_set_src(
                ria_mascot_object,
                ria_mascot_for_state(state)
            );
        }

        ria_mascot_apply_animation(state);
    }

    // RIA_ORBIT_FOCUS_MODE_V1
    if (ria_focus_overlay) {
        if (state == RIA_STATE_IDLE) {
            lv_obj_add_flag(
                ria_focus_overlay, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_obj_clear_flag(
                ria_focus_overlay, LV_OBJ_FLAG_HIDDEN);

            if (ria_focus_mascot) {
                // State image initializes each interaction.
                // The existing mouth timer replaces it with
                // audio-driven frames during playback.
                lv_img_set_src(
                    ria_focus_mascot,
                    ria_mascot_for_state(state)
                );
            }

            if (ria_focus_label) {
                const char *focus_text = "RIA";

                if (state == RIA_STATE_LISTENING)
                    focus_text = "Listening...";
                else if (state == RIA_STATE_THINKING)
                    focus_text = "Thinking...";
                else if (state == RIA_STATE_SPEAKING)
                    focus_text = "Speaking...";

                lv_label_set_text(
                    ria_focus_label, focus_text);
            }

            lv_obj_move_foreground(ria_focus_overlay);
        }
    }

}


// RIA_REMINDER_OVERLAY_V1
static lv_obj_t *ria_reminder_overlay = nullptr;
static lv_obj_t *ria_reminder_title_label = nullptr;

// RIA_ORBIT_HOME_REDESIGN_V1
static lv_obj_t *ria_clock_label = nullptr;
static lv_obj_t *ria_date_label = nullptr;
static lv_obj_t *ria_weather_label = nullptr;

// RIA_ORBIT_WEATHER_STATUS_V1
// RIA_ORBIT_VISUAL_POLISH_V2
static lv_obj_t *ria_weather_icon = nullptr;
static lv_obj_t *ria_weather_sun = nullptr;
static lv_obj_t *ria_weather_cloud = nullptr;
static lv_obj_t *ria_weather_cloud_top = nullptr;
static lv_obj_t *ria_weather_drop_1 = nullptr;
static lv_obj_t *ria_weather_drop_2 = nullptr;


static void ria_weather_icon_update(const char *weather)
{
    if (!ria_weather_sun || !ria_weather_cloud ||
        !ria_weather_cloud_top ||
        !ria_weather_drop_1 || !ria_weather_drop_2)
        return;

    const bool clear =
        weather && strstr(weather, "Clear");

    const bool partial =
        weather && strstr(weather, "Partly");

    const bool precipitation =
        weather &&
        (strstr(weather, "Rain") ||
         strstr(weather, "Drizzle") ||
         strstr(weather, "Storm") ||
         strstr(weather, "Snow"));

    lv_obj_t *parts[] = {
        ria_weather_sun,
        ria_weather_cloud,
        ria_weather_cloud_top,
        ria_weather_drop_1,
        ria_weather_drop_2
    };

    for (lv_obj_t *part : parts)
        lv_obj_add_flag(part, LV_OBJ_FLAG_HIDDEN);

    if (clear || partial) {
        lv_obj_clear_flag(
            ria_weather_sun, LV_OBJ_FLAG_HIDDEN);
    }

    if (!clear) {
        lv_obj_clear_flag(
            ria_weather_cloud, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(
            ria_weather_cloud_top, LV_OBJ_FLAG_HIDDEN);
    }

    if (precipitation) {
        lv_obj_clear_flag(
            ria_weather_drop_1, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(
            ria_weather_drop_2, LV_OBJ_FLAG_HIDDEN);
    }
}


static void ria_home_info_update(
    const char *clock_text,
    const char *date_text,
    const char *weather_text
) {
    if (ria_clock_label && clock_text)
        lv_label_set_text(ria_clock_label, clock_text);

    if (ria_date_label && date_text)
        lv_label_set_text(ria_date_label, date_text);

    if (ria_weather_label && weather_text) {
        
        
        // RIA_DYNAMIC_WEATHER_A3656B
        lv_label_set_text(ria_weather_label, weather_text);
        lv_obj_set_width(ria_weather_label, LV_SIZE_CONTENT);
        lv_obj_update_layout(ria_weather_label);

        const int right_edge = 470;
        const int icon_width = 27;
        const int gap = 6;
        const int min_icon_x = 205;

        int text_width = lv_obj_get_width(ria_weather_label);
        int icon_x = right_edge - text_width - gap - icon_width;

        if (icon_x < min_icon_x) {
            icon_x = min_icon_x;
            lv_obj_set_width(
                ria_weather_label,
                right_edge - icon_x - icon_width - gap
            );
            lv_label_set_long_mode(
                ria_weather_label,
                LV_LABEL_LONG_DOT
            );
        }

        lv_obj_set_pos(ria_weather_icon, icon_x, 12);
        lv_obj_set_pos(
            ria_weather_label,
            icon_x + icon_width + gap,
            18
        );



        if (ria_weather_icon)
            ria_weather_icon_update(weather_text);
    }
}


// RIA_ORBIT_UPCOMING_V1
// RIA_UPCOMING_DYNAMIC_ROWS_V1
// RIA_ORBIT_INFOBAR_V1
static lv_obj_t *ria_mic_button = nullptr;
static lv_obj_t *ria_upcoming_panel = nullptr;
static lv_obj_t *ria_upcoming_divider = nullptr;
static lv_obj_t *ria_upcoming_title_1 = nullptr;
static lv_obj_t *ria_upcoming_time_1 = nullptr;
static lv_obj_t *ria_upcoming_title_2 = nullptr;
static lv_obj_t *ria_upcoming_time_2 = nullptr;

static void ria_upcoming_update(
    const char titles[2][48],
    const char times[2][16]
) {
    if (!ria_upcoming_title_1 ||
        !ria_upcoming_time_1 ||
        !ria_upcoming_title_2 ||
        !ria_upcoming_time_2)
        return;

    lv_label_set_text(ria_upcoming_title_1, titles[0]);
    lv_label_set_text(ria_upcoming_time_1, times[0]);
    lv_label_set_text(ria_upcoming_title_2, titles[1]);
    lv_label_set_text(ria_upcoming_time_2, times[1]);

    const bool has_second_row = titles[1][0] != '\0';

    if (has_second_row) {
        lv_obj_clear_flag(
            ria_upcoming_title_2, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(
            ria_upcoming_time_2, LV_OBJ_FLAG_HIDDEN);
        if (ria_upcoming_divider)
            lv_obj_clear_flag(
                ria_upcoming_divider, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(
            ria_upcoming_title_2, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(
            ria_upcoming_time_2, LV_OBJ_FLAG_HIDDEN);
        if (ria_upcoming_divider)
            lv_obj_add_flag(
                ria_upcoming_divider, LV_OBJ_FLAG_HIDDEN);
    }

    if (ria_upcoming_panel)
        lv_obj_set_height(
            ria_upcoming_panel,
            has_second_row ? 119 : 70);

    if (ria_mic_button)
        lv_obj_set_y(
            ria_mic_button,
            has_second_row ? 155 : 130);

}




#include "ria_memory_confirm.h"

// RIA_INTERACTIVE_REMINDERS_V1
// 0=None, 1=Done, 2=Snooze, 3=Skip
static volatile int ria_reminder_action_requested = 0;
static volatile bool ria_reminder_action_enabled = false;
static lv_obj_t *ria_reminder_instruction = nullptr;


// RIA_REMINDER_INTERRUPT_V1
static bool ria_reminder_interrupt_pending(void)
{
    return __atomic_load_n(
        &ria_reminder_action_enabled, __ATOMIC_ACQUIRE
    ) && __atomic_load_n(
        &ria_reminder_action_requested, __ATOMIC_ACQUIRE
    ) != 0;
}

static void ria_reminder_action_clicked(lv_event_t *event)
{
    // RIA_REMINDER_TOUCH_DIAG_V1
    ESP_LOGI(
        "RIA_TOUCH",
        "Reminder button event received, enabled=%d",
        (int)__atomic_load_n(
            &ria_reminder_action_enabled, __ATOMIC_ACQUIRE
        )
    );

    if (!__atomic_load_n(
        &ria_reminder_action_enabled, __ATOMIC_ACQUIRE))
        return;

    int action = (int)(intptr_t)lv_event_get_user_data(event);

    if (action >= 1 && action <= 3) {
        ESP_LOGI(
            "RIA_TOUCH",
            "Reminder action selected: %d", action
        );
        int expected = 0;
        __atomic_compare_exchange_n(
            &ria_reminder_action_requested,
            &expected, action, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE
        );
    }
}

// RIA_REMINDER_PRESERVE_EARLY_ACTION_V1
static void ria_reminder_overlay_ready(void)
{
    // Preserve a button press made while RIA was speaking.
    __atomic_store_n(
        &ria_reminder_action_enabled, true, __ATOMIC_RELEASE);

    if (ria_reminder_instruction)
        lv_label_set_text(
            ria_reminder_instruction,
            "Touch Done, Snooze or Skip"
        );
}

static void ria_reminder_overlay_saving(void)
{
    __atomic_store_n(
        &ria_reminder_action_enabled, false, __ATOMIC_RELEASE);

    if (ria_reminder_instruction)
        lv_label_set_text(
            ria_reminder_instruction, "Saving..."
        );
}

static void ria_reminder_overlay_action_failed(void)
{
    if (ria_reminder_instruction)
        lv_label_set_text(
            ria_reminder_instruction, "Action failed - try again"
        );

    __atomic_store_n(
        &ria_reminder_action_requested, 0, __ATOMIC_RELEASE);
    __atomic_store_n(
        &ria_reminder_action_enabled, true, __ATOMIC_RELEASE);
}


// RIA_REMINDER_CONTEXT_V2
// Presentation only: keep SQLite titles untouched.
static void ria_title_case_display(char *value)
{
    if (!value)
        return;

    bool new_word = true;

    for (char *p = value; *p; ++p) {
        if (*p == ' ' || *p == '-' || *p == '_') {
            new_word = true;
        } else {
            if (new_word && *p >= 'a' && *p <= 'z')
                *p = (char)(*p - 'a' + 'A');

            new_word = false;
        }
    }
}

static void ria_reminder_overlay_show(const char *title)
{
    if (!ria_reminder_overlay || !ria_reminder_title_label)
        return;

    __atomic_store_n(
        &ria_reminder_action_enabled, false, __ATOMIC_RELEASE);
    __atomic_store_n(
        &ria_reminder_action_requested, 0, __ATOMIC_RELEASE);

    if (ria_reminder_instruction)
        lv_label_set_text(
            ria_reminder_instruction, "Announcing reminder..."
        );

    char display_title[201] = {};
    snprintf(
        display_title, sizeof(display_title),
        "%s", title ? title : "Reminder"
    );
    ria_title_case_display(display_title);

    lv_label_set_text(
        ria_reminder_title_label,
        display_title
    );

    // RIA_REMINDER_TOUCH_IMMEDIATE_V2
    // Accept touchscreen selections immediately.
    __atomic_store_n(
        &ria_reminder_action_enabled,
        true, __ATOMIC_RELEASE
    );

    lv_obj_clear_flag(
        ria_reminder_overlay,
        LV_OBJ_FLAG_HIDDEN
    );
    // RIA_REMINDER_EARLY_TOUCH_V1
    // Enable touch actions during reminder announcement.
    // The audio task processes the selected action safely.
    __atomic_store_n(
        &ria_reminder_action_enabled,
        true,
        __ATOMIC_RELEASE
    );

    if (ria_reminder_instruction)
        lv_label_set_text(
            ria_reminder_instruction,
            "Touch Done, Snooze or Skip"
        );

    lv_obj_move_foreground(ria_reminder_overlay);
}

static void ria_reminder_overlay_hide(void)
{
    if (ria_reminder_overlay) {
        lv_obj_add_flag(
            ria_reminder_overlay,
            LV_OBJ_FLAG_HIDDEN
        );
    }
}


static lv_color_t ria_color(uint32_t hex)
{
    return lv_color_hex(hex);
}

static lv_obj_t *ria_panel(
    lv_obj_t *parent,
    int x, int y, int w, int h,
    uint32_t color, int radius = 12)
{
    lv_obj_t *obj = lv_obj_create(parent);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_bg_color(obj, ria_color(color), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(obj, radius, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_clear_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    return obj;
}

static lv_obj_t *ria_text(
    lv_obj_t *parent,
    const char *value,
    int x, int y,
    uint32_t color)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, value);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_style_text_color(label, ria_color(color), 0);
    // RIA_ORBIT_ACCESSIBILITY_FONT_V1
    lv_obj_set_style_text_font(
        label, &lv_font_montserrat_16, 0);
    return label;
}

static void ria_on_action(lv_event_t *event)
{
    const char *action =
        (const char *)lv_event_get_user_data(event);

    if (action != nullptr &&
        strcmp(action, "Microphone tapped") == 0) {
        ria_mic_requests = true;
        if (ria_status != nullptr) {
            lv_label_set_text(ria_status, "Listening...");
            lv_obj_clear_flag(
                ria_status, LV_OBJ_FLAG_HIDDEN);
            if (ria_activity_strip)
                lv_obj_clear_flag(
                    ria_activity_strip, LV_OBJ_FLAG_HIDDEN);
        }
        return;
    }

    if (ria_status != nullptr) {
        lv_label_set_text(ria_status, action);
    }
}

static lv_obj_t *ria_button(
    lv_obj_t *parent,
    const char *title,
    const char *message,
    int x, int y, int w, int h,
    uint32_t accent)
{
    lv_obj_t *button = lv_btn_create(parent);
    lv_obj_set_pos(button, x, y);
    lv_obj_set_size(button, w, h);

    lv_obj_set_style_bg_color(
        button, ria_color(0x17243F), 0);
    lv_obj_set_style_bg_opa(
        button, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(
        button, ria_color(accent), 0);
    lv_obj_set_style_border_width(button, 2, 0);
    lv_obj_set_style_radius(button, 12, 0);
    lv_obj_set_style_shadow_width(button, 0, 0);

    lv_obj_add_event_cb(
        button, ria_on_action,
        LV_EVENT_CLICKED, (void *)message);

    lv_obj_t *label = lv_label_create(button);
    lv_label_set_text(label, title);
    lv_obj_set_style_text_color(
        label, ria_color(0xFFFFFF), 0);
    lv_obj_set_style_text_font(
        label, &lv_font_montserrat_20, 0);
    lv_obj_center(label);
    return button;
}


static void ria_mascot_float_cb(void *obj, int32_t y)
{
    lv_obj_set_y((lv_obj_t *)obj, y);
}

static void ria_home_create(void)
{
    lv_obj_t *screen = lv_scr_act();

    lv_obj_set_style_bg_color(
        screen, ria_color(0x071225), 0);
    lv_obj_set_style_bg_opa(
        screen, LV_OPA_COVER, 0);
    lv_obj_clear_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    // LEFT: Approved RIA mascot artwork
    lv_obj_t *mascot = lv_img_create(screen);
    lv_img_set_src(mascot, ria_mascot_for_state(RIA_STATE_IDLE));
    lv_obj_set_pos(mascot, 11, 76);

    ria_mascot_object = mascot;
    lv_timer_create(ria_real_mouth_timer, 80, nullptr);
    ria_current_visual_state = RIA_STATE_IDLE;
    ria_mascot_apply_animation(RIA_STATE_IDLE);

    lv_obj_t *ria_name = ria_text(
        screen, "R I A", 0, 0, 0xFFFFFF);
    lv_obj_set_width(ria_name, 136);
    lv_obj_set_style_text_align(
        ria_name, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(ria_name, 11, 223);

    // RIGHT: Greeting
    // Top information bar
    ria_clock_label = ria_text(
        screen, "--:--", 14, 10, 0xFFFFFF);
    lv_obj_set_style_text_font(
        ria_clock_label, &lv_font_montserrat_20, 0);

    ria_date_label = ria_text(
        screen, "Date unavailable", 14, 36, 0xA4C7FF);
    lv_obj_set_style_text_font(
        ria_date_label, &lv_font_montserrat_12, 0);

    // Draw weather icon with LVGL shapes instead of
    // unsupported emoji/font symbols.
    ria_weather_icon = lv_obj_create(screen);
    lv_obj_set_pos(ria_weather_icon, 282, 12);
    lv_obj_set_size(ria_weather_icon, 27, 27);
    lv_obj_set_style_bg_opa(
        ria_weather_icon, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ria_weather_icon, 0, 0);
    lv_obj_set_style_pad_all(ria_weather_icon, 0, 0);
    lv_obj_set_style_shadow_width(ria_weather_icon, 0, 0);
    lv_obj_clear_flag(
        ria_weather_icon, LV_OBJ_FLAG_SCROLLABLE);

    auto make_weather_shape = [](
        lv_obj_t *parent,
        int x, int y, int w, int ht,
        uint32_t color, int radius
    ) -> lv_obj_t * {
        lv_obj_t *shape = lv_obj_create(parent);
        lv_obj_set_pos(shape, x, y);
        lv_obj_set_size(shape, w, ht);
        lv_obj_set_style_bg_color(
            shape, lv_color_hex(color), 0);
        lv_obj_set_style_bg_opa(shape, LV_OPA_COVER, 0);
        lv_obj_set_style_radius(shape, radius, 0);
        lv_obj_set_style_border_width(shape, 0, 0);
        lv_obj_set_style_pad_all(shape, 0, 0);
        lv_obj_set_style_shadow_width(shape, 0, 0);
        lv_obj_clear_flag(
            shape, LV_OBJ_FLAG_SCROLLABLE);
        return shape;
    };

    ria_weather_sun = make_weather_shape(
        ria_weather_icon, 3, 2, 17, 17,
        0xFFD66B, LV_RADIUS_CIRCLE);

    ria_weather_cloud = make_weather_shape(
        ria_weather_icon, 3, 10, 23, 11,
        0xBDE9FF, LV_RADIUS_CIRCLE);

    ria_weather_cloud_top = make_weather_shape(
        ria_weather_icon, 9, 5, 14, 14,
        0xBDE9FF, LV_RADIUS_CIRCLE);

    ria_weather_drop_1 = make_weather_shape(
        ria_weather_icon, 9, 21, 3, 5,
        0x58D8FF, LV_RADIUS_CIRCLE);

    ria_weather_drop_2 = make_weather_shape(
        ria_weather_icon, 18, 21, 3, 5,
        0x58D8FF, LV_RADIUS_CIRCLE);

    ria_weather_icon_update("Cloudy");

    ria_weather_label = ria_text(
        screen, "Weather --", 315, 18, 0x8EEBFF);
    lv_obj_set_style_text_font(
        ria_weather_label, &lv_font_montserrat_16, 0);

    // RIA_WEATHER_BOUNDS_A3654
    // Keep dynamic weather descriptions inside the display.
    lv_obj_set_width(ria_weather_label, LV_SIZE_CONTENT);
    lv_label_set_long_mode(
        ria_weather_label, LV_LABEL_LONG_DOT
    );


    // Greeting in central content area
    lv_obj_t *ria_greeting = ria_text(
        screen, "Hi Kiran!", 167, 94, 0x8EEBFF);
    lv_obj_set_style_text_font(
        ria_greeting, &lv_font_montserrat_20, 0);


    // Reminder panel
    ria_upcoming_panel = ria_panel(
        screen, 164, 130, 214, 119,
        0x131F3B, 12);

    ria_text(screen, "REMINDERS", 177, 139,
             0x83A9EA);
    ria_upcoming_title_1 = ria_text(screen, "Loading...", 179, 167,
             0xFFFFFF);
    ria_upcoming_time_1 = ria_text(screen, "", 317, 167,
             0xA4C7FF);

    ria_upcoming_divider = ria_panel(
        screen, 177, 192, 188, 1,
        0x354869, 0);

    ria_upcoming_title_2 = ria_text(screen, "", 179, 208,
             0xFFFFFF);
    ria_upcoming_time_2 = ria_text(screen, "", 321, 208,
             0xA4C7FF);

    // Hide empty row on initial render.
    lv_obj_add_flag(
        ria_upcoming_title_2, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(
        ria_upcoming_time_2, LV_OBJ_FLAG_HIDDEN);
    if (ria_upcoming_divider)
        lv_obj_add_flag(
            ria_upcoming_divider, LV_OBJ_FLAG_HIDDEN);
    if (ria_upcoming_panel)
        lv_obj_set_height(ria_upcoming_panel, 70);

    // Microphone button: UI only for now
    ria_mic_button = ria_button(
        screen, "MIC", "Microphone tapped",
        393, 130, 69, 69, 0x58D8FF);

    // Four quick actions








    // Touch-feedback/status area
    ria_activity_strip = ria_panel(
        screen, 124, 265, 232, 42,
        0x17243F, 14);

    ria_status = ria_text(
        ria_activity_strip, "", 0, 11, 0xFFFFFF);

    lv_obj_set_width(ria_status, 232);
    lv_obj_set_style_text_align(
        ria_status, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(
        ria_status, &lv_font_montserrat_16, 0);
    lv_obj_add_flag(
        ria_status, LV_OBJ_FLAG_HIDDEN);
    if (ria_activity_strip)
        lv_obj_add_flag(
            ria_activity_strip, LV_OBJ_FLAG_HIDDEN);

    // Temporary reminder notification, hidden by default.
    ria_reminder_overlay = ria_panel(
        screen, 78, 67, 324, 184,
        0x17243F, 18
    );

    lv_obj_set_style_border_color(
        ria_reminder_overlay,
        ria_color(0x58D8FF), 0
    );
    lv_obj_set_style_border_width(
        ria_reminder_overlay, 2, 0
    );

    ria_text(
        ria_reminder_overlay,
        "RIA  |  REMINDER",
        19, 15, 0x8EEBFF
    );

    ria_reminder_title_label = ria_text(
        ria_reminder_overlay,
        "Reminder",
        20, 63, 0xFFFFFF
    );

    lv_obj_set_width(ria_reminder_title_label, 284);
    lv_label_set_long_mode(
        ria_reminder_title_label,
        LV_LABEL_LONG_WRAP
    );
    lv_obj_set_style_text_align(
        ria_reminder_title_label,
        LV_TEXT_ALIGN_CENTER, 0
    );

    ria_reminder_instruction = ria_text(
        ria_reminder_overlay,
        "Announcing reminder...",
        30, 115, 0xA4C7FF
    );
    lv_obj_set_width(ria_reminder_instruction, 264);
    lv_obj_set_style_text_align(
        ria_reminder_instruction, LV_TEXT_ALIGN_CENTER, 0
    );


    // RIA_INTERACTIVE_REMINDERS_V1
    const char *action_titles[] = {"Done", "Snooze", "Skip"};
    const uint32_t action_colors[] = {
        0x205648, 0x554522, 0x433747
    };

    for (int i = 0; i < 3; i++) {
        lv_obj_t *button = lv_obj_create(ria_reminder_overlay);

        lv_obj_set_pos(button, 9 + i * 103, 140);
        lv_obj_set_size(button, 98, 44);
        lv_obj_set_style_bg_color(
            button, lv_color_hex(action_colors[i]), 0
        );
        lv_obj_set_style_bg_opa(button, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(button, 0, 0);
        lv_obj_set_style_radius(button, 9, 0);
        lv_obj_set_style_pad_all(button, 0, 0);
        lv_obj_clear_flag(button, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_add_flag(button, LV_OBJ_FLAG_CLICKABLE);

        lv_obj_add_event_cb(
            button,
            ria_reminder_action_clicked,
            LV_EVENT_CLICKED,
            (void *)(intptr_t)(i + 1)
        );

        lv_obj_t *label = lv_label_create(button);
        lv_label_set_text(label, action_titles[i]);
        lv_obj_set_style_text_color(
            label, lv_color_hex(0xFFFFFF), 0
        );
        lv_obj_center(label);
    }

    ria_reminder_overlay_hide();

    // RIA_ORBIT_FOCUS_MODE_V1
    ria_focus_overlay = lv_obj_create(screen);
    lv_obj_set_pos(ria_focus_overlay, 0, 0);
    lv_obj_set_size(ria_focus_overlay, 480, 320);
    lv_obj_set_style_bg_color(
        ria_focus_overlay, lv_color_hex(0x071225), 0);
    lv_obj_set_style_bg_opa(
        ria_focus_overlay, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(ria_focus_overlay, 0, 0);
    lv_obj_set_style_radius(ria_focus_overlay, 0, 0);
    lv_obj_set_style_pad_all(ria_focus_overlay, 0, 0);
    lv_obj_clear_flag(
        ria_focus_overlay, LV_OBJ_FLAG_SCROLLABLE);

    ria_focus_mascot = lv_img_create(ria_focus_overlay);
    lv_img_set_src(
        ria_focus_mascot,
        ria_mascot_for_state(RIA_STATE_LISTENING));
    // RIA_FOCUS_CENTER_V2
    // LVGL image scale: 256 = 100%, 333 = ~130%.
    lv_img_set_zoom(ria_focus_mascot, 333);

    // Center both horizontally and vertically.
    // Slight upward offset leaves room for status text.
    lv_obj_align(
        ria_focus_mascot,
        LV_ALIGN_CENTER,
        0,
        -25
    );

    ria_focus_label = lv_label_create(ria_focus_overlay);
    lv_label_set_text(ria_focus_label, "Listening...");
    lv_obj_set_style_text_color(
        ria_focus_label, lv_color_hex(0x8EEBFF), 0);
    lv_obj_set_style_text_font(
        ria_focus_label, &lv_font_montserrat_20, 0);
    lv_obj_align(
        ria_focus_label,
        LV_ALIGN_CENTER, 0, 100);

    lv_obj_add_flag(
        ria_focus_overlay, LV_OBJ_FLAG_HIDDEN);

}
