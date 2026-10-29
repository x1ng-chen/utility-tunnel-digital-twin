#include "sdkconfig.h"
#include "provisioning.h"

#if !CONFIG_UTILITY_TUNNEL_OFFLINE_WAKE_TEST
#include "application.h"
#include "board.h"
#include "display.h"
#include <driver/uart.h>
#include <esp_log.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <nvs.h>
#include <cJSON.h>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>

namespace UtilityTunnelVoice {
namespace {
constexpr const char* kTag = "VoiceProvision";
constexpr size_t kMaxLine = 1024;
portMUX_TYPE gate_lock = portMUX_INITIALIZER_UNLOCKED;
int64_t gate_until = 0;
bool uart_ready = false;

bool StateAllowsProvisioning() {
    auto state = Application::GetInstance().GetDeviceState();
    return state == kDeviceStateStarting || state == kDeviceStateWifiConfiguring ||
           state == kDeviceStateActivating;
}
bool GateOpen() {
    portENTER_CRITICAL(&gate_lock);
    const bool open = gate_until != 0 && esp_timer_get_time() < gate_until;
    if (!open) gate_until = 0;
    portEXIT_CRITICAL(&gate_lock);
    return open && StateAllowsProvisioning();
}
void CloseGate() {
    portENTER_CRITICAL(&gate_lock);
    gate_until = 0;
    portEXIT_CRITICAL(&gate_lock);
}
bool PrivateOtaUrl(const std::string& url) {
    unsigned a, b, c, d, port;
    int used = 0;
    if (std::sscanf(url.c_str(), "http://%u.%u.%u.%u:%u/xiaozhi/ota/%n",
                    &a, &b, &c, &d, &port, &used) != 5 ||
        used != static_cast<int>(url.size()) || port != 8942 ||
        a > 255 || b > 255 || c > 255 || d > 255) return false;
    if (!(a == 10 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168))) return false;
    const std::string canonical = "http://" + std::to_string(a) + "." + std::to_string(b) +
        "." + std::to_string(c) + "." + std::to_string(d) + ":8942/xiaozhi/ota/";
    return canonical == url;
}
bool FlatObject(const std::string& line) {
    bool quoted = false, escaped = false;
    int depth = 0;
    for (unsigned char ch : line) {
        if (ch == 0) return false;
        if (quoted) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') quoted = false;
        } else {
            if (ch == '"') quoted = true;
            else if (ch == '[' || ch == ']') return false;
            else if (ch == '{') { if (++depth > 1) return false; }
            else if (ch == '}') { if (--depth < 0) return false; }
        }
    }
    return !quoted && depth == 0;
}
bool Store(const std::string& line) {
    if (!FlatObject(line)) return false;
    const char* end = nullptr;
    cJSON* root = cJSON_ParseWithLengthOpts(line.c_str(), line.size() + 1, &end, true);
    if (!cJSON_IsObject(root)) { cJSON_Delete(root); return false; }
    bool unique = true;
    unsigned mask = 0;
    for (auto* child = root->child; child; child = child->next) {
        unsigned bit = 0;
        if (child->string && std::strcmp(child->string, "type") == 0) bit = 1;
        else if (child->string && std::strcmp(child->string, "version") == 0) bit = 2;
        else if (child->string && std::strcmp(child->string, "ota_url") == 0) bit = 4;
        else if (child->string && std::strcmp(child->string, "token") == 0) bit = 8;
        if (bit == 0 || (mask & bit)) unique = false;
        mask |= bit;
    }
    auto* type = cJSON_GetObjectItemCaseSensitive(root, "type");
    auto* version = cJSON_GetObjectItemCaseSensitive(root, "version");
    auto* ota = cJSON_GetObjectItemCaseSensitive(root, "ota_url");
    auto* token = cJSON_GetObjectItemCaseSensitive(root, "token");
    bool valid = unique && mask == 15 && cJSON_IsString(type) &&
        std::strcmp(type->valuestring, "ut.voice.provision") == 0 &&
        cJSON_IsNumber(version) && version->valuedouble == 1 &&
        cJSON_IsString(ota) && cJSON_IsString(token);
    if (valid) {
        const size_t token_length = std::strlen(token->valuestring);
        valid = token_length == 64 && std::all_of(token->valuestring, token->valuestring + token_length,
            [](unsigned char ch) { return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f'); }) &&
            PrivateOtaUrl(ota->valuestring);
    }
    bool stored = false;
    if (valid && GateOpen()) {
        CloseGate();
        nvs_handle_t handle = 0;
        esp_err_t result = nvs_open("voice_access", NVS_READWRITE, &handle);
        if (result == ESP_OK) result = nvs_set_str(handle, "token", token->valuestring);
        if (result == ESP_OK) result = nvs_set_str(handle, "ota_url", ota->valuestring);
        if (result == ESP_OK) result = nvs_commit(handle);
        if (handle) nvs_close(handle);
        stored = result == ESP_OK;
    }
    if (cJSON_IsString(token)) {
        std::memset(token->valuestring, 0, std::strlen(token->valuestring));
    }
    cJSON_Delete(root);
    return stored;
}
void Receive(void*) {
    std::string line;
    line.reserve(kMaxLine);
    bool overflow = false;
    uint8_t bytes[64];
    for (;;) {
        const int count = uart_read_bytes(UART_NUM_0, bytes, sizeof(bytes), pdMS_TO_TICKS(100));
        if (!GateOpen()) {
            std::fill(line.begin(), line.end(), '\0');
            line.clear();
            overflow = false;
            continue;
        }
        for (int i = 0; i < count; ++i) {
            const char ch = static_cast<char>(bytes[i]);
            if (ch == '\r') continue;
            if (ch != '\n') {
                if (!overflow && line.size() < kMaxLine - 1) line.push_back(ch);
                else { overflow = true; std::fill(line.begin(), line.end(), '\0'); line.clear(); }
                continue;
            }
            bool stored = false;
            if (!overflow && !line.empty()) stored = Store(line);
            std::fill(line.begin(), line.end(), '\0');
            line.clear();
            overflow = false;
            if (stored) {
                ESP_LOGI(kTag, "UT VOICE PROVISION: saved; rebooting");
                vTaskDelay(pdMS_TO_TICKS(250));
                esp_restart();
            } else {
                ESP_LOGW(kTag, "UT VOICE PROVISION: rejected");
            }
        }
        std::memset(bytes, 0, sizeof(bytes));
    }
}
}
void InitializeProvisioning() {
    uart_config_t config = {};
    config.baud_rate = 115200;
    config.data_bits = UART_DATA_8_BITS;
    config.parity = UART_PARITY_DISABLE;
    config.stop_bits = UART_STOP_BITS_1;
    config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    config.source_clk = UART_SCLK_XTAL;
    esp_err_t result = uart_param_config(UART_NUM_0, &config);
    if (result == ESP_OK && !uart_is_driver_installed(UART_NUM_0)) {
        result = uart_driver_install(UART_NUM_0, 2048, 0, 0, nullptr, 0);
    }
    if (result == ESP_OK) {
        uart_ready = xTaskCreate(Receive, "voice_provision", 6144, nullptr, 2, nullptr) == pdPASS;
    }
    ESP_LOGI(kTag, "USB provisioning: %s; hold BOOT 2s during WiFi setup",
             uart_ready ? "ready" : "unavailable");
}
void ArmProvisioning() {
    if (!uart_ready || !StateAllowsProvisioning()) return;
    uart_flush_input(UART_NUM_0);
    portENTER_CRITICAL(&gate_lock);
    gate_until = esp_timer_get_time() + 60LL * 1000 * 1000;
    portEXIT_CRITICAL(&gate_lock);
    ESP_LOGI(kTag, "UT VOICE PROVISION: window_open, seconds=60");
    Application::GetInstance().Schedule([]() {
        Board::GetInstance().GetDisplay()->ShowNotification("串口配置已开启", 60000);
    });
}
}
#else
namespace UtilityTunnelVoice {
void InitializeProvisioning() {}
void ArmProvisioning() {}
}
#endif
