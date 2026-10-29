#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "provisioning.h"
#include "mcp_server.h"
#include "settings.h"
#include "display/oled_display.h"

#include <driver/i2c_master.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <esp_log.h>

LV_FONT_DECLARE(BUILTIN_TEXT_FONT);

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
        Settings settings("audio", false);
        const int saved = std::clamp(static_cast<int>(settings.GetInt("output_volume", VOICE_START_VOLUME)), 0, VOICE_MAX_VOLUME);
        AudioCodec::Start();
        // Base Start treats mute as invalid; this terminal deliberately preserves 0.
        if (output_volume() != saved) AudioCodec::SetOutputVolume(saved);
    }

    void SetOutputVolume(int volume) override {
        const int value = std::clamp(volume, 0, VOICE_MAX_VOLUME);
        if (value == output_volume()) return;
        if (value > 0) { Settings settings("audio", true); settings.SetInt("last_volume", value); }
        AudioCodec::SetOutputVolume(value);
    }
};

class TunnelOledDisplay final : public OledDisplay {
private:
    lv_obj_t* face_ = nullptr;
    lv_obj_t* eyes_[2] = {nullptr, nullptr};
    lv_obj_t* pupils_[2] = {nullptr, nullptr};
    lv_obj_t* text_panel_ = nullptr;
    lv_obj_t* speech_panel_ = nullptr;
    lv_obj_t* mouth_ = nullptr;
    lv_obj_t* mouth_inner_ = nullptr;
    lv_obj_t* waves_[6] = {};
    bool last_speaking_ = false;
    int last_speech_frame_ = -1;
    lv_obj_t* status_text_ = nullptr;
    lv_obj_t* chat_text_ = nullptr;
    lv_timer_t* face_timer_ = nullptr;
    int blend_ = 0;
    int last_blend_ = -1;
    bool last_blink_ = false;
    bool last_idle_ = false;

    static int Mix(int a, int b, int amount) { return (a * (100 - amount) + b * amount + 50) / 100; }
    static void SetHidden(lv_obj_t* obj, bool hidden) {
        if (hidden) lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN);
        else lv_obj_remove_flag(obj, LV_OBJ_FLAG_HIDDEN);
    }
    void Render() {
        auto& app = Application::GetInstance();
        const auto state = app.GetDeviceState();
        const bool idle = state == kDeviceStateIdle;
        // TTS can stop sending before the speaker's buffered audio is drained.
        const bool speaking = !idle && (state == kDeviceStateSpeaking || !app.GetAudioService().IsPlaybackIdle());
        const int frame = speaking ? (lv_tick_get() / 160) % 8 : -1;
        const int target = idle ? 0 : 100;
        if (blend_ < target) blend_ = std::min(target, blend_ + 34);
        if (blend_ > target) blend_ = std::max(target, blend_ - 34);
        const bool blink = (lv_tick_get() % 5100) < 100;
        if (blend_ == last_blend_ && blink == last_blink_ && idle == last_idle_ &&
            speaking == last_speaking_ && frame == last_speech_frame_) return;
        last_blend_ = blend_; last_blink_ = blink; last_idle_ = idle;
        last_speaking_ = speaking; last_speech_frame_ = frame;
        SetHidden(text_panel_, idle || blend_ < 100 || speaking);
        SetHidden(speech_panel_, idle || blend_ < 100 || !speaking);
        if (speaking) {
            constexpr int heights[8] = {4, 9, 16, 11, 6, 13, 18, 8};
            const int h = heights[frame];
            lv_obj_set_size(mouth_, 22, h); lv_obj_set_pos(mouth_, 31, (32-h)/2);
            lv_obj_set_style_radius(mouth_, h/2, 0);
            SetHidden(mouth_inner_, h < 7);
            if (h >= 7) {
                lv_obj_set_size(mouth_inner_, 14, h-6); lv_obj_set_pos(mouth_inner_, 4, 3);
                lv_obj_set_style_radius(mouth_inner_, (h-6)/2, 0);
            }
            for (int i = 0; i < 6; ++i) {
                const int wh = heights[(frame+i*2)%8];
                lv_obj_set_size(waves_[i], 3, wh);
                lv_obj_set_pos(waves_[i], i<3 ? 6+i*7 : 62+(i-3)*7, (32-wh)/2);
            }
        }
        for (int i = 0; i < 2; ++i) {
            const int x = Mix(i == 0 ? 4 : 70, i == 0 ? 3 : 21, blend_);
            const int w = Mix(54, 12, blend_);
            const int normal_h = Mix(28, 18, blend_);
            const int h = blink ? 2 : normal_h;
            lv_obj_set_pos(eyes_[i], x, (32 - h) / 2);
            lv_obj_set_size(eyes_[i], w, h);
            lv_obj_set_style_radius(eyes_[i], blink ? 1 : Mix(9, 5, blend_), 0);
            SetHidden(pupils_[i], blink);
            if (!blink) {
                const int pw = Mix(12, 4, blend_), ph = Mix(16, 8, blend_);
                lv_obj_set_size(pupils_[i], pw, ph);
                lv_obj_set_pos(pupils_[i], (w - pw) / 2, (h - ph) / 2);
                lv_obj_set_style_radius(pupils_[i], pw / 2, 0);
            }
        }
    }
    static void Timer(lv_timer_t* timer) {
        static_cast<TunnelOledDisplay*>(lv_timer_get_user_data(timer))->Render();
    }
public:
    using OledDisplay::OledDisplay;
    bool IsReady() const { return display_ != nullptr; }
    ~TunnelOledDisplay() override {
        if (face_ != nullptr) {
            DisplayLockGuard lock(this);
            if (lock) {
                if (face_timer_) lv_timer_delete(face_timer_);
                lv_obj_delete(face_);
                face_ = nullptr; face_timer_ = nullptr;
            }
        }
    }
    void SetupUI() override {
        if (setup_ui_called_) return;
        OledDisplay::SetupUI();
        DisplayLockGuard lock(this);
        if (!lock || !display_) return;
        face_ = lv_obj_create(lv_screen_active());
        lv_obj_remove_style_all(face_);
        lv_obj_set_size(face_, 128, 32); lv_obj_set_pos(face_, 0, 0);
        lv_obj_set_style_bg_color(face_, lv_color_black(), 0);
        lv_obj_set_style_bg_opa(face_, LV_OPA_COVER, 0);
        lv_obj_clear_flag(face_, LV_OBJ_FLAG_SCROLLABLE);
        for (int i = 0; i < 2; ++i) {
            eyes_[i] = lv_obj_create(face_); lv_obj_remove_style_all(eyes_[i]);
            lv_obj_set_style_bg_color(eyes_[i], lv_color_white(), 0);
            lv_obj_set_style_bg_opa(eyes_[i], LV_OPA_COVER, 0);
            lv_obj_clear_flag(eyes_[i], LV_OBJ_FLAG_SCROLLABLE);
            pupils_[i] = lv_obj_create(eyes_[i]); lv_obj_remove_style_all(pupils_[i]);
            lv_obj_set_style_bg_color(pupils_[i], lv_color_black(), 0);
            lv_obj_set_style_bg_opa(pupils_[i], LV_OPA_COVER, 0);
            lv_obj_clear_flag(pupils_[i], LV_OBJ_FLAG_SCROLLABLE);
        }
        text_panel_ = lv_obj_create(face_); lv_obj_remove_style_all(text_panel_);
        lv_obj_set_pos(text_panel_, 40, 0); lv_obj_set_size(text_panel_, 88, 32);
        lv_obj_set_style_bg_color(text_panel_, lv_color_black(), 0);
        lv_obj_set_style_bg_opa(text_panel_, LV_OPA_COVER, 0);
        lv_obj_clear_flag(text_panel_, LV_OBJ_FLAG_SCROLLABLE);
        status_text_ = lv_label_create(text_panel_); chat_text_ = lv_label_create(text_panel_);
        for (auto* label : {status_text_, chat_text_}) {
            lv_obj_set_size(label, 88, 16);
            lv_obj_set_style_text_color(label, lv_color_white(), 0);
            // Inherit the screen font, including downloaded Chinese glyphs.
            lv_label_set_long_mode(label, LV_LABEL_LONG_SCROLL_CIRCULAR);
            lv_label_set_text(label, "");
        }
        lv_obj_set_pos(status_text_, 0, 0); lv_obj_set_pos(chat_text_, 0, 16);
        speech_panel_ = lv_obj_create(face_); lv_obj_remove_style_all(speech_panel_);
        lv_obj_set_pos(speech_panel_, 40, 0); lv_obj_set_size(speech_panel_, 88, 32);
        lv_obj_set_style_bg_color(speech_panel_, lv_color_black(), 0);
        lv_obj_set_style_bg_opa(speech_panel_, LV_OPA_COVER, 0);
        lv_obj_clear_flag(speech_panel_, LV_OBJ_FLAG_SCROLLABLE);
        mouth_ = lv_obj_create(speech_panel_); lv_obj_remove_style_all(mouth_);
        lv_obj_set_style_bg_color(mouth_, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(mouth_, LV_OPA_COVER, 0);
        lv_obj_clear_flag(mouth_, LV_OBJ_FLAG_SCROLLABLE);
        mouth_inner_ = lv_obj_create(mouth_); lv_obj_remove_style_all(mouth_inner_);
        lv_obj_set_style_bg_color(mouth_inner_, lv_color_black(), 0);
        lv_obj_set_style_bg_opa(mouth_inner_, LV_OPA_COVER, 0);
        lv_obj_clear_flag(mouth_inner_, LV_OBJ_FLAG_SCROLLABLE);
        for (auto& wave : waves_) {
            wave=lv_obj_create(speech_panel_); lv_obj_remove_style_all(wave);
            lv_obj_set_style_bg_color(wave, lv_color_white(), 0);
            lv_obj_set_style_bg_opa(wave, LV_OPA_COVER, 0);
            lv_obj_set_style_radius(wave, 1, 0);
            lv_obj_clear_flag(wave, LV_OBJ_FLAG_SCROLLABLE);
        }
        SetHidden(speech_panel_, true);
        face_timer_ = lv_timer_create(Timer, 100, this);
        Render();
    }
    void SetStatus(const char* status) override {
        DisplayLockGuard lock(this); if (!lock || !status_text_) return;
        if (Application::GetInstance().GetDeviceState() == kDeviceStateIdle) return;
        lv_label_set_text(status_text_, status ? status : "");
        Render();
    }
    void SetChatMessage(const char*, const char* text) override {
        DisplayLockGuard lock(this); if (!lock || !chat_text_) return;
        if (Application::GetInstance().GetDeviceState() == kDeviceStateIdle) return;
        std::string value = text ? text : "";
        std::replace(value.begin(), value.end(), '\n', ' ');
        lv_label_set_text(chat_text_, value.c_str());
        Render();
    }
    void ClearChatMessages() override {
        DisplayLockGuard lock(this); if (lock && chat_text_) lv_label_set_text(chat_text_, "");
    }
    void RemoveChatMessage(const char*, const char* text) override {
        DisplayLockGuard lock(this);
        if (lock && chat_text_ && text && std::string(lv_label_get_text(chat_text_)) == text) lv_label_set_text(chat_text_, "");
    }
    void ShowNotification(const char* text, int = 3000) override { SetStatus(text); }
    void ShowNotification(const std::string& text, int duration_ms = 3000) override { ShowNotification(text.c_str(), duration_ms); }
    bool SetEmotion(const char*) override { return face_ != nullptr; }
    void UpdateStatusBar(bool = false) override {}
};

class UtilityTunnelS3Board final : public WifiBoard {
private:
    Button boot_button_;
    Display* display_ = nullptr;
    i2c_master_bus_handle_t display_i2c_bus_ = nullptr;

    void InitializeAudioTools() {
        auto& mcp = McpServer::GetInstance();
        mcp.AddTool("self.audio_speaker.get_volume", "Get this terminal's current and maximum volume.", PropertyList(),
            [this](const PropertyList&) -> ToolResult {
                const auto state = Application::GetInstance().GetDeviceState();
                if (state != kDeviceStateListening && state != kDeviceStateSpeaking) return std::unexpected(std::string("Session no longer active"));
                Settings settings("audio", false);
                const int previous = std::clamp(static_cast<int>(settings.GetInt("last_volume", VOICE_START_VOLUME)), 1, VOICE_MAX_VOLUME);
                return ReturnValue(std::string("{\"volume\":") + std::to_string(GetAudioCodec()->output_volume()) +
                    ",\"max_volume\":" + std::to_string(VOICE_MAX_VOLUME) + ",\"unmute_volume\":" + std::to_string(previous) + "}");
            });
        mcp.AddTool("self.audio_speaker.set_volume", "Set only the voice terminal speaker volume.",
            PropertyList({Property("volume", kPropertyTypeInteger, 0, VOICE_MAX_VOLUME)}),
            [this](const PropertyList& properties) -> ToolResult {
                const auto state = Application::GetInstance().GetDeviceState();
                if (state != kDeviceStateListening && state != kDeviceStateSpeaking) return std::unexpected(std::string("Session no longer active"));
                GetAudioCodec()->SetOutputVolume(properties["volume"].value<int>());
                return ReturnValue(true);
            });
    }

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
        InitializeAudioTools();
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
