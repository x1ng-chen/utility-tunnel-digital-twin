#ifndef UTILITY_TUNNEL_S3_CONFIG_H
#define UTILITY_TUNNEL_S3_CONFIG_H

#include <driver/gpio.h>

// Dedicated voice terminal. Do not use GPIO35-37 on the N16R8 module.
#define AUDIO_INPUT_SAMPLE_RATE 16000
// MAX98357A supports 48 kHz; do not copy the reference board's 24 kHz.
#define AUDIO_OUTPUT_SAMPLE_RATE 48000

// Separate I2S buses, left channel on both the microphone and amplifier.
#define AUDIO_I2S_MIC_GPIO_WS GPIO_NUM_4
#define AUDIO_I2S_MIC_GPIO_SCK GPIO_NUM_5
#define AUDIO_I2S_MIC_GPIO_DIN GPIO_NUM_6
#define AUDIO_I2S_SPK_GPIO_DOUT GPIO_NUM_7
#define AUDIO_I2S_SPK_GPIO_BCLK GPIO_NUM_15
#define AUDIO_I2S_SPK_GPIO_LRCK GPIO_NUM_16

#define BOOT_BUTTON_GPIO GPIO_NUM_0

// User-requested volume 80; keep startup and runtime volume consistent.
#define VOICE_START_VOLUME 80
#define VOICE_MAX_VOLUME 80

// Provisional SSD1306-compatible 128x32 OLED. Probe before enabling it.
#define UTILITY_TUNNEL_OLED_ENABLED 1
#define DISPLAY_SDA_PIN GPIO_NUM_41
#define DISPLAY_SCL_PIN GPIO_NUM_42
#define DISPLAY_WIDTH 128
#define DISPLAY_HEIGHT 32
#define DISPLAY_MIRROR_X false
#define DISPLAY_MIRROR_Y false
// The board RGB LED remains unused.
#endif
