#pragma once

#include <stdint.h>

// RIA_MEMORY_CONFIRM_UI_V1
// UI-only confirmation. No database or HTTP operations.

// 0 = waiting, 1 = confirm, 2 = cancel
static volatile int ria_memory_decision = 0;
static lv_obj_t *ria_memory_overlay = nullptr;
static lv_obj_t *ria_memory_fact_label = nullptr;

static void ria_memory_button_clicked(lv_event_t *event)
{
    int choice = (int)(intptr_t)lv_event_get_user_data(event);

    if (choice != 1 && choice != 2)
        return;

    // Record only the first touch.
    int expected = 0;
    __atomic_compare_exchange_n(
        &ria_memory_decision,
        &expected,
        choice,
        false,
        __ATOMIC_ACQ_REL,
        __ATOMIC_ACQUIRE
    );

    if (ria_memory_overlay)
        lv_obj_add_flag(
            ria_memory_overlay,
            LV_OBJ_FLAG_HIDDEN
        );
}

static inline void ria_memory_confirm_show(const char *fact)
{
    // Must be called from the LVGL UI thread or while
    // holding the existing LVGL display lock.

    if (!ria_memory_overlay) {
        ria_memory_overlay = lv_obj_create(lv_scr_act());

        lv_obj_set_size(ria_memory_overlay, 380, 232);
        lv_obj_center(ria_memory_overlay);

        lv_obj_set_style_bg_color(
            ria_memory_overlay,
            lv_color_hex(0x17243F), 0
        );

        lv_obj_set_style_bg_opa(
            ria_memory_overlay, LV_OPA_COVER, 0
        );

        lv_obj_set_style_radius(
            ria_memory_overlay, 18, 0
        );

        lv_obj_set_style_border_width(
            ria_memory_overlay, 2, 0
        );

        lv_obj_set_style_border_color(
            ria_memory_overlay,
            lv_color_hex(0x58D8FF), 0
        );

        lv_obj_clear_flag(
            ria_memory_overlay,
            LV_OBJ_FLAG_SCROLLABLE
        );

        lv_obj_t *heading = lv_label_create(
            ria_memory_overlay
        );

        lv_label_set_text(
            heading, "RIA | MEMORY"
        );

        lv_obj_set_style_text_color(
            heading, lv_color_hex(0x8EEBFF), 0
        );

        lv_obj_align(
            heading, LV_ALIGN_TOP_MID, 0, 10
        );

        ria_memory_fact_label = lv_label_create(
            ria_memory_overlay
        );

        lv_obj_set_width(ria_memory_fact_label, 335);
        lv_label_set_long_mode(
            ria_memory_fact_label, LV_LABEL_LONG_WRAP
        );

        lv_obj_set_style_text_color(
            ria_memory_fact_label,
            lv_color_hex(0xFFFFFF), 0
        );

        lv_obj_set_style_text_align(
            ria_memory_fact_label,
            LV_TEXT_ALIGN_CENTER, 0
        );

        lv_obj_align(
            ria_memory_fact_label,
            LV_ALIGN_TOP_MID, 0, 53
        );

        const char *titles[] = {
            "Cancel", "Confirm"
        };

        const uint32_t colors[] = {
            0x433747, 0x205648
        };

        for (int i = 0; i < 2; i++) {
            lv_obj_t *button = lv_btn_create(
                ria_memory_overlay
            );

            lv_obj_set_size(button, 145, 43);

            lv_obj_align(
                button,
                LV_ALIGN_BOTTOM_MID,
                i == 0 ? -81 : 81,
                -10
            );

            lv_obj_set_style_bg_color(
                button, lv_color_hex(colors[i]), 0
            );

            lv_obj_add_event_cb(
                button,
                ria_memory_button_clicked,
                LV_EVENT_CLICKED,
                (void *)(intptr_t)(i == 0 ? 2 : 1)
            );

            lv_obj_t *label = lv_label_create(button);
            lv_label_set_text(label, titles[i]);
            lv_obj_center(label);
        }
    }

    __atomic_store_n(
        &ria_memory_decision, 0, __ATOMIC_RELEASE
    );

    lv_label_set_text(
        ria_memory_fact_label,
        fact ? fact : "Review this memory change"
    );

    lv_obj_move_foreground(ria_memory_overlay);
    lv_obj_clear_flag(
        ria_memory_overlay,
        LV_OBJ_FLAG_HIDDEN
    );
}

static inline int ria_memory_confirm_take_decision(void)
{
    return __atomic_exchange_n(
        &ria_memory_decision,
        0,
        __ATOMIC_ACQ_REL
    );
}
