#include <stddef.h>
#pragma once

#include <stdio.h>
#include "driver/i2c_master.h"

void esp_es8311_port_init(i2c_master_bus_handle_t bus_handle);
void esp_es8311_test(void);


// Returns a PSRAM-allocated 48 kHz mono 16-bit PCM buffer.
// Caller must release it using heap_caps_free().
uint8_t *ria_capture_audio(size_t *out_size);

// Play 48 kHz, mono, signed 16-bit PCM.
bool ria_play_pcm(const uint8_t *pcm, size_t pcm_size);

// Streaming playback interface.
// Input: 48 kHz, signed 16-bit, mono PCM.
bool ria_stream_begin(void);
bool ria_stream_write(const uint8_t *pcm, size_t pcm_size);
void ria_stream_end(void);

