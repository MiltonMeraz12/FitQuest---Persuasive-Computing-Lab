#pragma once

// Copy this file to wifi_config.h and set values for your local test network.
// Keep wifi_config.h private because it contains Wi-Fi credentials.
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";

// Default: broadcast telemetry so the laptop IP can change between hotspots.
#define TELEMETRY_USE_BROADCAST 1

// Optional fixed-IP fallback. Only used when TELEMETRY_USE_BROADCAST is 0.
IPAddress TELEMETRY_DESTINATION_IP(192, 168, 1, 100);
