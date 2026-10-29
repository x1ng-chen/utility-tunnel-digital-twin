#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "provisioning.h"
#include "display/oled_display.h"

#include <driver/i2c_master.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <esp_log.h>

namespace {
constexpr const char* kTag = "UtilityTunnelVoice";

class TunnelVoiceCodec final : public NoAudioCodecSimplex {
#if CONFIG_UTILITY_TUNNEL_OFFLINE_WAKE_TEST
private:
    uint64_t test_energy_ = 0;
    uint32_t test_samples_ = 0;
    uint32_t test_peak_ = 0;

protected:
    int Read(int16_t* data, int samples) override {
        const int count = NoAudioCodec::Read(data, samples);
        for (int i = 0; i < count; ++i) {
            const int32_t value = data[i];
            test_energy_ += static_cast<uint64_t>(static_cast<int64_t>(value) * value);
            test_peak_ = std::max(test_peak_, static_cast<uint32_t>(value < 0 ? -value : value));
        }
        test_samples_ += count;
        if (test_samples_ >= AUDIO_INPUT_SAMPLE_RATE) {
            const auto rms = static_cast<unsigned>(
                std::sqrt(static_cast<double>(test_energy_) / test_samples_));
            ESP_LOGI(kTag, "OFFLINE MIC: samples=%u rms=%u peak=%u",
                     static_cast<unsigned>(test_samples_), rms,
                     static_cast<unsigned>(test_peak_));
            test_energy_ = 0;
            test_samples_ = 0;
            test_peak_ = 0;
        }
        return count;
    }
#endif

#if CONFIG_UTILITY_TUNNEL_SPEAKER_TEST
protected:
    int Write(const int16_t* data, int samples) override {
        const int count = NoAudioCodec::Write(data, samples);
        ESP_LOGI(kTag, "OFFLINE SPEAKER TX: samples=%d volume=%d", count, output_volume());
        return count;
    }
#endif

public:
    TunnelVoiceCodec()
        : NoAudioCodecSimplex(
              AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
              AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK,
              AUDIO_I2S_SPK_GPIO_DOUT, AUDIO_I2S_MIC_GPIO_SCK,
              AUDIO_I2S_MIC_GPIO_WS, AUDIO_I2S_MIC_GPIO_DIN) {}

    void Start() override {
        AudioCodec::Start();
        // Apply the user's requested fixed volume before any output is enabled.
        SetOutputVolume(VOICE_START_VOLUME);
    }

    void SetOutputVolume(int volume) override {
        AudioCodec::SetOutputVolume(std::clamp(volume, 0, VOICE_MAX_VOLUME));
    }
};

class TunnelOledDisplay final : public OledDisplay {
public:
    using OledDisplay::OledDisplay;
    bool IsReady() const { return display_ != nullptr; }
};

class UtilityTunnelS3Board final : public WifiBoard {
private:
    Button boot_button_;
    Display* display_ = nullptr;
    i2c_master_bus_handle_t display_i2c_bus_ = nullptr;

    void InitializeDisplay() {
#if UTILITY_TUNNEL_OLED_ENABLED
        i2c_master_bus_config_t bus_config = {};
        bus_config.i2c_port = I2C_NUM_0;
        bus_config.sda_io_num = DISPLAY_SDA_PIN;
        bus_config.scl_io_num = DISPLAY_SCL_PIN;
        bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
        bus_config.glitch_ignore_cnt = 7;
        bus_config.flags.enable_internal_pullup = true;
        auto result = i2c_new_master_bus(&bus_config, &display_i2c_bus_);
        if (result != ESP_OK) {
            ESP_LOGW(kTag, "OLED unavailable: I2C init %s; continuing audio only", esp_err_to_name(result));
            return;
        }

        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;
        auto cleanup = [&]() {
            if (panel != nullptr) esp_lcd_panel_del(panel);
            if (panel_io != nullptr) esp_lcd_panel_io_del(panel_io);
            if (display_i2c_bus_ != nullptr) {
                i2c_del_master_bus(display_i2c_bus_);
                display_i2c_bus_ = nullptr;
            }
        };
        uint8_t address = 0;
        for (uint8_t candidate : {0x3c, 0x3d}) {
            result = i2c_master_probe(display_i2c_bus_, candidate, 100);
            if (result == ESP_OK) {
                address = candidate;
                break;
            }
            if (result == ESP_ERR_TIMEOUT) break;
        }
        if (address == 0) {
            ESP_LOGW(kTag, "OLED unavailable: no response at 0x3c/0x3d; continuing audio only");
            cleanup();
            return;
        }
        ESP_LOGI(kTag, "OLED detected: address=0x%02x SDA=41 SCL=42; trying SSD1306 128x32", address);
        esp_lcd_panel_io_i2c_config_t io_config = {};
        io_config.dev_addr = address;
        io_config.scl_speed_hz = 100000;
        io_config.control_phase_bytes = 1;
        io_config.dc_bit_offset = 6;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        result = esp_lcd_new_panel_io_i2c(display_i2c_bus_, &io_config, &panel_io);
        esp_lcd_panel_ssd1306_config_t vendor_config = {};
        vendor_config.height = DISPLAY_HEIGHT;
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = GPIO_NUM_NC;
        panel_config.bits_per_pixel = 1;
        panel_config.vendor_config = &vendor_config;
        if (result == ESP_OK) result = esp_lcd_new_panel_ssd1306(panel_io, &panel_config, &panel);
        if (result == ESP_OK) result = esp_lcd_panel_reset(panel);
        if (result == ESP_OK) result = esp_lcd_panel_init(panel);
        if (result == ESP_OK) result = esp_lcd_panel_invert_color(panel, false);
        if (result == ESP_OK) result = esp_lcd_panel_disp_on_off(panel, true);
        if (result != ESP_OK) {
            ESP_LOGW(kTag, "OLED unavailable: panel init %s; continuing audio only", esp_err_to_name(result));
            cleanup();
            return;
        }
        auto* oled = new TunnelOledDisplay(panel_io, panel, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                          DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
        // The display owns the panel and IO from this point, including on failure.
        panel = nullptr;
        panel_io = nullptr;
        if (!oled->IsReady()) {
            delete oled;
            cleanup();
            ESP_LOGW(kTag, "OLED unavailable: LVGL init; continuing audio only");
            return;
        }
        display_ = oled;
        ESP_LOGI(kTag, "OLED ready: provisional SSD1306-compatible 128x32");
#endif
    }

public:
    UtilityTunnelS3Board() : boot_button_(BOOT_BUTTON_GPIO, false, 2000) {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
#if CONFIG_UTILITY_TUNNEL_OFFLINE_WAKE_TEST
            app.ToggleChatState();
#else
            if (app.GetDeviceState() == kDeviceStateStarting) {
                EnterWifiConfigMode();
                return;
            }
            app.ToggleChatState();
#endif
        });
        InitializeDisplay();
#if !CONFIG_UTILITY_TUNNEL_OFFLINE_WAKE_TEST
        UtilityTunnelVoice::InitializeProvisioning();
        boot_button_.OnLongPress([this]() {
            auto state = Application::GetInstance().GetDeviceState();
            if (state == kDeviceStateIdle || state == kDeviceStateListening ||
                state == kDeviceStateSpeaking) {
                EnterWifiConfigMode();
                return;
            }
            UtilityTunnelVoice::ArmProvisioning();
        });
#endif
        // No demo GPIO tools or RGB LED.
        ESP_LOGI(kTag, "Dedicated voice board: mic 16k, speaker 48k, OLED=%s",
                 display_ != nullptr ? "enabled" : "unavailable");
    }

    Display* GetDisplay() override {
        return display_ != nullptr ? display_ : Board::GetDisplay();
    }

    AudioCodec* GetAudioCodec() override {
        static TunnelVoiceCodec codec;
        return &codec;
    }
};
}  // namespace

DECLARE_BOARD(UtilityTunnelS3Board);
