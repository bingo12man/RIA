#include <atomic>
#include <string.h>
#include <cstring>
#include <math.h>
#include "esp_idf_version.h"

#include "driver/i2s_std.h"
#include "driver/i2s_tdm.h"
#include "soc/soc_caps.h"

#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"


#include "driver/i2c_master.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

#include "esp_heap_caps.h"


#define USE_IDF_I2C_MASTER


#define I2S_MCK_PIN 12  // MCLK 引脚
#define I2S_BCK_PIN 13  // BCLK 引脚
#define I2S_LRCK_PIN 15 // LRCLK 引脚
#define I2S_DOUT_PIN 16 // 数据输出（录制）
#define I2S_DIN_PIN 14  // 数据输入（播放）

i2s_chan_handle_t tx_handle;
i2s_chan_handle_t rx_handle;
esp_codec_dev_handle_t output_dev;
esp_codec_dev_handle_t input_dev;

static esp_err_t es8311_i2s_init(void)
{
    esp_err_t esp_err;
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    i2s_std_config_t std_cfg = {};
    std_cfg.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000);
    std_cfg.slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG((i2s_data_bit_width_t)16, I2S_SLOT_MODE_STEREO);

    std_cfg.gpio_cfg.mclk = (gpio_num_t)I2S_MCK_PIN;
    std_cfg.gpio_cfg.bclk = (gpio_num_t)I2S_BCK_PIN;
    std_cfg.gpio_cfg.ws = (gpio_num_t)I2S_LRCK_PIN;
    std_cfg.gpio_cfg.dout = (gpio_num_t)I2S_DOUT_PIN;
    std_cfg.gpio_cfg.din = (gpio_num_t)I2S_DIN_PIN;

    esp_err = i2s_new_channel(&chan_cfg, &tx_handle, &rx_handle);

    esp_err = i2s_channel_init_std_mode(tx_handle, &std_cfg);

    esp_err = i2s_channel_init_std_mode(rx_handle, &std_cfg);
    // For tx master using duplex mode
    i2s_channel_enable(tx_handle);
    i2s_channel_enable(rx_handle);

    return esp_err;
}

void esp_es8311_port_init(i2c_master_bus_handle_t bus_handle)
{
    es8311_i2s_init();
    audio_codec_i2s_cfg_t i2s_cfg = {
        .rx_handle = rx_handle,
        .tx_handle = tx_handle,
    };
    const audio_codec_data_if_t *data_if = audio_codec_new_i2s_data(&i2s_cfg);

    static audio_codec_i2c_cfg_t i2c_cfg = {};
    i2c_cfg.addr = ES8311_CODEC_DEFAULT_ADDR;
    i2c_cfg.bus_handle = bus_handle;

    const audio_codec_ctrl_if_t *ctrl_if = audio_codec_new_i2c_ctrl(&i2c_cfg);

    const audio_codec_gpio_if_t *gpio_if = audio_codec_new_gpio();
    // New output codec interface
    es8311_codec_cfg_t es8311_cfg = {};
    es8311_cfg.codec_mode = ESP_CODEC_DEV_WORK_MODE_BOTH;
    es8311_cfg.ctrl_if = ctrl_if;
    es8311_cfg.gpio_if = gpio_if;
    es8311_cfg.pa_pin = GPIO_NUM_NC;
    es8311_cfg.use_mclk = true;
    es8311_cfg.hw_gain.pa_voltage = 5.0;
    es8311_cfg.hw_gain.codec_dac_voltage = 3.3;

    const audio_codec_if_t *codec_if = es8311_codec_new(&es8311_cfg);

    static  esp_codec_dev_cfg_t dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_OUT,
        .codec_if = codec_if,
        .data_if = data_if,
    };
    output_dev = esp_codec_dev_new(&dev_cfg);
    assert(output_dev != NULL);

    dev_cfg.dev_type = ESP_CODEC_DEV_TYPE_IN;
    input_dev = esp_codec_dev_new(&dev_cfg);
    assert(input_dev != NULL);
    esp_codec_set_disable_when_closed(output_dev, false);
    esp_codec_set_disable_when_closed(input_dev, false);

    esp_codec_dev_sample_info_t fs = {};
    fs.sample_rate = 48000;
    fs.channel = 1;
    fs.bits_per_sample = 16;
    fs.channel_mask = 0;
    fs.mclk_multiple = 0;

    esp_codec_dev_open(output_dev, &fs);
    esp_codec_dev_open(input_dev, &fs);
}




// Capture microphone PCM for later WAV upload.
// Caller owns the returned PSRAM buffer and must free it.

// RIA_DYNAMIC_CAPTURE_V1
// 48 kHz / PCM16 / mono.
// Stop 2.5 seconds after speech ends.
// Maximum 60 seconds; no-speech timeout 10 seconds.
// Caller owns returned PSRAM allocation.
uint8_t *ria_capture_audio(size_t *out_size)
{
    if (out_size == NULL)
        return NULL;

    *out_size = 0;

    const size_t sample_rate = 48000;
    const size_t frame_ms = 20;
    const size_t samples_per_frame =
        sample_rate * frame_ms / 1000;
    const size_t frame_bytes = samples_per_frame * 2;

    const size_t max_frames = 60000 / frame_ms;
    const size_t idle_frames = 10000 / frame_ms;
    const size_t silence_frames = 2500 / frame_ms;
    // RIA_VAD_BACKGROUND_GUARD_V3
    const size_t max_speech_frames = 18000 / frame_ms;
    const size_t preroll_frames = 300 / frame_ms;
    const size_t attack_frames = 15;

    const size_t max_bytes = max_frames * frame_bytes;

    printf("RIA_VAD: starting dynamic capture\n");
    printf("RIA_VAD: PSRAM largest block=%u\n",
        (unsigned)heap_caps_get_largest_free_block(
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));

    uint8_t *data = (uint8_t *)heap_caps_malloc(
        max_bytes,
        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
    );

    if (data == NULL) {
        printf("RIA_VAD: PSRAM allocation failed (%u bytes)\n",
            (unsigned)max_bytes);
        return NULL;
    }

    int16_t frame[samples_per_frame];

    size_t frames_written = 0;
    size_t speech_start = 0;
    size_t speech_detected_frame = 0;
    size_t active_frames = 0;
    size_t quiet_frames = 0;
    // RIA_VAD_SUSTAINED_ACTIVITY_V4
    size_t continuation_frames = 0;
    const size_t continuation_required = 200 / frame_ms;
    size_t candidate_frames = 0;

    bool speech_detected = false;
    bool capture_failed = false;

    // Initial estimate; updated only during quiet frames.
    float noise_floor = 80.0f;
    const float minimum_threshold = 700.0f;
    const float noise_multiplier = 4.0f;

    esp_codec_dev_set_in_gain(input_dev, 40.0);

    while (frames_written < max_frames) {

        int err = esp_codec_dev_read(
            input_dev,
            frame,
            frame_bytes
        );

        if (err != ESP_CODEC_DEV_OK) {
            printf("RIA_VAD: codec read failed %d\n", err);
            capture_failed = true;
            break;
        }

        // RMS energy of 20 ms PCM16 audio.
        double sum = 0.0;

        for (size_t i = 0; i < samples_per_frame; ++i) {
            double v = (double)frame[i];
            sum += v * v;
        }

        float rms = sqrtf(
            (float)(sum / samples_per_frame)
        );

        memcpy(
            data + frames_written * frame_bytes,
            frame,
            frame_bytes
        );

        ++frames_written;

        float threshold = noise_floor * noise_multiplier;

        if (threshold < minimum_threshold)
            threshold = minimum_threshold;

        // RIA_VAD_NOISE_GUARD_V2
        // Require stronger energy to START speaking.
        // Use a lower threshold to keep ongoing quiet syllables.
        const float continuation_threshold =
            threshold * 0.85f;
        bool loud_frame = rms >= (
            speech_detected
                ? continuation_threshold
                : threshold
        );

        if (!speech_detected) {

            if (loud_frame) {
                ++candidate_frames;
            } else {
                candidate_frames = 0;

                // Learn background noise gradually.
                noise_floor =
                    noise_floor * 0.98f + rms * 0.02f;
            }

            if (candidate_frames >= attack_frames) {
                speech_detected = true;
                speech_detected_frame = frames_written;

                size_t detected_start =
                    frames_written - candidate_frames;

                speech_start =
                    detected_start > preroll_frames
                        ? detected_start - preroll_frames
                        : 0;

                active_frames = frames_written;
                quiet_frames = 0;

                printf(
                    "RIA_VAD: speech detected at %u ms, RMS=%.0f, threshold=%.0f\n",
                    (unsigned)(frames_written * frame_ms),
                    (double)rms,
                    (double)threshold
                );
            }

            if (!speech_detected &&
                frames_written >= idle_frames) {
                printf(
                    "RIA_VAD: no speech timeout, noise=%.0f threshold=%.0f\n",
                    (double)noise_floor,
                    (double)threshold
                );
                break;
            }

        } else {

            if (loud_frame) {
                ++continuation_frames;

                if (continuation_frames >=
                    continuation_required) {
                    active_frames = frames_written;
                    quiet_frames = 0;
                }
            } else {
                continuation_frames = 0;
                ++quiet_frames;
            }

            if (frames_written - active_frames >=
                silence_frames) {
                printf("RIA_VAD: end of speech detected\n");
                break;
            }

            if (frames_written - speech_detected_frame >=
                max_speech_frames) {
                printf(
                    "RIA_VAD: background guard reached 18-second cap\n"
                );
                break;
            }
        }
    }

    // Always restore input gain.
    esp_codec_dev_set_in_gain(input_dev, 0.0);

    if (capture_failed || !speech_detected) {
        heap_caps_free(data);
        return NULL;
    }

    size_t bytes_written =
        frames_written * frame_bytes;

    size_t start_bytes =
        speech_start * frame_bytes;

    size_t final_bytes =
        bytes_written - start_bytes;

    if (start_bytes > 0) {
        memmove(data, data + start_bytes, final_bytes);
    }

    if (final_bytes == 0) {
        heap_caps_free(data);
        return NULL;
    }

    *out_size = final_bytes;

    printf(
        "RIA_VAD: recording complete duration=%.2f sec bytes=%u\n",
        (double)final_bytes / 96000.0,
        (unsigned)final_bytes
    );

    return data;
}



// Play 48 kHz, mono, signed 16-bit PCM through ES8311.
// Applies playback-only gain without modifying the caller's data.
// RIA_REAL_MOUTH_SYNC_V2
std::atomic<uint8_t> ria_mouth_level{0};
std::atomic<bool> ria_audio_playing{false};


// RIA_REMINDER_INTERRUPT_V1
extern "C" bool ria_reminder_stop_playback_requested(void);

bool ria_play_pcm(const uint8_t *pcm, size_t pcm_size)
{
    if (pcm == NULL || pcm_size == 0 ||
        (pcm_size % 2) != 0) {
        return false;
    }

    const size_t chunk_bytes = 4096;

    uint8_t *chunk = (uint8_t *)heap_caps_malloc(
        chunk_bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
    );

    if (chunk == NULL) {
        printf("RIA_SPEAKER: allocation failed\n");
        return false;
    }

    ria_mouth_level.store(0);
    ria_audio_playing.store(true);
    esp_codec_dev_set_out_vol(output_dev, 100.0);

    bool success = true;

    for (size_t offset = 0; offset < pcm_size;
         offset += chunk_bytes) {
        // RIA_REMINDER_INTERRUPT_V1
        // Never interrupt ordinary conversation playback.
        if (ria_reminder_stop_playback_requested()) {
            success = false;
            printf("RIA_SPEAKER: reminder interrupted by touch\n");
            break;
        }


        size_t count = pcm_size - offset;

        if (count > chunk_bytes)
            count = chunk_bytes;

        memcpy(chunk, pcm + offset, count);

        int16_t *samples = (int16_t *)chunk;
        size_t sample_count = count / sizeof(int16_t);

        for (size_t i = 0; i < sample_count; ++i) {
            int32_t value = (int32_t)(
                (float)samples[i] * 1.3f
            );

            if (value > 32767) value = 32767;
            if (value < -32768) value = -32768;

            samples[i] = (int16_t)value;
        }

        // RIA_REAL_MOUTH_SYNC_V2
        // Read audio energy; do not alter speaker samples.
        uint64_t energy = 0;
        size_t measured = 0;

        for (size_t i = 0; i < sample_count; i += 16) {
            int32_t value = samples[i];
            energy += (uint64_t)(
                (int64_t)value * value
            );
            ++measured;
        }

        const uint64_t mean =
            measured ? energy / measured : 0;

        const uint8_t level =
            mean > 2200ULL * 2200ULL ? 2 :
            mean > 650ULL * 650ULL ? 1 : 0;

        ria_mouth_level.store(
            level,
            std::memory_order_relaxed
        );


        int err = esp_codec_dev_write(
            output_dev, chunk, count
        );

        if (err != ESP_CODEC_DEV_OK) {
            printf("RIA_SPEAKER: write failed %d\n", err);
            success = false;
            break;
        }
    }

    ria_audio_playing.store(false);
    ria_mouth_level.store(0);
    esp_codec_dev_set_out_vol(output_dev, 0.0);
    heap_caps_free(chunk);

    printf("RIA_SPEAKER: playback %s (%u bytes)\n",
           success ? "complete" : "failed",
           (unsigned)pcm_size);

    return success;
}


// Streaming PCM playback. One active session at a time.
// Do not call concurrently with ria_play_pcm().

static uint8_t *ria_stream_chunk = nullptr;
static bool ria_stream_active = false;
static const size_t RIA_STREAM_CHUNK_BYTES = 4096;

bool ria_stream_begin(void)
{
    if (ria_stream_active || ria_stream_chunk != nullptr)
        return false;

    ria_stream_chunk = (uint8_t *)heap_caps_malloc(
        RIA_STREAM_CHUNK_BYTES,
        MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
    );

    if (ria_stream_chunk == nullptr) {
        printf("RIA_STREAM: buffer allocation failed\n");
        return false;
    }

    if (esp_codec_dev_set_out_vol(output_dev, 100.0)
        != ESP_CODEC_DEV_OK) {
        printf("RIA_STREAM: volume enable failed\n");
        heap_caps_free(ria_stream_chunk);
        ria_stream_chunk = nullptr;
        return false;
    }

    ria_stream_active = true;
    printf("RIA_STREAM: started\n");
    return true;
}

bool ria_stream_write(const uint8_t *pcm, size_t pcm_size)
{
    if (!ria_stream_active ||
        ria_stream_chunk == nullptr ||
        pcm == nullptr ||
        pcm_size == 0 ||
        (pcm_size % 2) != 0) {
        return false;
    }

    for (size_t offset = 0;
         offset < pcm_size;
         offset += RIA_STREAM_CHUNK_BYTES) {

        size_t count = pcm_size - offset;

        if (count > RIA_STREAM_CHUNK_BYTES)
            count = RIA_STREAM_CHUNK_BYTES;

        memcpy(ria_stream_chunk, pcm + offset, count);

        // RIA_A33318_UNITY_GAIN
        // Mac streaming proxy already normalizes and limits PCM.
        // Preserve incoming PCM16 without additional gain.

        int err = esp_codec_dev_write(
            output_dev,
            ria_stream_chunk,
            count
        );

        if (err != ESP_CODEC_DEV_OK) {
            printf("RIA_STREAM: write failed %d\n", err);
            return false;
        }
    }

    return true;
}

void ria_stream_end(void)
{
    if (ria_stream_active)
        esp_codec_dev_set_out_vol(output_dev, 0.0);

    ria_stream_active = false;

    if (ria_stream_chunk != nullptr) {
        heap_caps_free(ria_stream_chunk);
        ria_stream_chunk = nullptr;
    }

    printf("RIA_STREAM: stopped\n");
}

void esp_es8311_test(void)
{
    int err = 0;
    // 2 Sec
    const int limit_size = 2 * 48000 * 1 * (16 >> 3);

    uint8_t *data = (uint8_t *)heap_caps_malloc(limit_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    esp_codec_dev_set_in_gain(input_dev, 40.0);
    err = esp_codec_dev_read(input_dev, data, limit_size);
    esp_codec_dev_set_in_gain(input_dev, 0.0);

    if (err == ESP_CODEC_DEV_OK && data != NULL)
    {
        const int16_t *samples = (const int16_t *)data;
        const size_t count = limit_size / sizeof(int16_t);

        int peak = 0;
        double sum_squares = 0.0;

        for (size_t i = 0; i < count; ++i)
        {
            int sample = (int)samples[i];
            int amplitude = sample < 0 ? -sample : sample;

            if (amplitude > peak)
                peak = amplitude;

            sum_squares += (double)sample * sample;
        }

        double rms = sqrt(sum_squares / count);

        printf("RIA_AUDIO_LEVEL peak=%d rms=%.1f\\n",
               peak, rms);
    }

    
    if (err == ESP_CODEC_DEV_OK)
        printf("Read %d bytes\n", limit_size);
    else
        printf("Read error %d\n", err);
    

    // RIA_DIGITAL_GAIN: modest playback-only amplification
    if (err == ESP_CODEC_DEV_OK && data != NULL)
    {
        int16_t *samples = (int16_t *)data;
        const size_t count = limit_size / sizeof(int16_t);

        for (size_t i = 0; i < count; ++i)
        {
            int32_t value = (int32_t)(
                (float)samples[i] * 1.3f
            );

            if (value > 32767)
                value = 32767;
            if (value < -32768)
                value = -32768;

            samples[i] = (int16_t)value;
        }

        printf("RIA_DIGITAL_GAIN factor=1.3\\n");
    }

    esp_codec_dev_set_out_vol(output_dev, 100.0);
    err = esp_codec_dev_write(output_dev, data, limit_size);
    esp_codec_dev_set_out_vol(output_dev, 0.0);
    if (err == ESP_CODEC_DEV_OK)
        printf("Write %d bytes\n", limit_size);
    else
        printf("Write error %d\n", err);
    
    heap_caps_free(data);
}