#pragma once

// Copy this file to secrets.h and fill in the Wi-Fi and optional local MQTT
// credentials. The broker address is discovered automatically over UDP and is
// intentionally not compiled into the firmware. secrets.h is ignored by Git.
#define WIFI_SSID "replace-me"
#define WIFI_PASSWORD "replace-me"
#define MQTT_USERNAME ""
#define MQTT_PASSWORD ""
#define DISCOVERY_HMAC_KEY "replace-with-the-same-random-key-as-the-gateway"

