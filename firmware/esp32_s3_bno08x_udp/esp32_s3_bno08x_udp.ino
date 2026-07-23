#include <Adafruit_BNO08x.h>
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <math.h>

// For local Wi-Fi values, copy wifi_config.example.h to wifi_config.h
// in this folder and keep wifi_config.h out of shared project files.
#if __has_include("wifi_config.h")
#include "wifi_config.h"
#else
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
IPAddress TELEMETRY_DESTINATION_IP(192, 168, 1, 100);
#endif

#ifndef TELEMETRY_USE_BROADCAST
#define TELEMETRY_USE_BROADCAST 1
#endif

// Falls back to a placeholder if an older wifi_config.h does not define one
// yet. Set a real private value in wifi_config.h (gitignored) before relying
// on this for anything beyond a desk test.
#ifndef DISCOVERY_TOKEN
constexpr char DISCOVERY_TOKEN[] = "CHANGE_ME_SHARED_SECRET";
#endif

constexpr uint16_t TELEMETRY_DESTINATION_PORT = 4210;
constexpr uint16_t LOCAL_UDP_PORT = 4211;

constexpr int SDA_PIN = 8;
constexpr int SCL_PIN = 9;
constexpr uint8_t BNO08X_I2C_ADDRESS = 0x4B;
constexpr int BNO08X_RESET = -1;
constexpr unsigned long BNO08X_BOOT_DELAY_MS = 1500;
constexpr uint8_t BNO08X_INIT_ATTEMPTS = 20;
constexpr unsigned long BNO08X_INIT_RETRY_DELAY_MS = 300;
constexpr unsigned long TELEMETRY_INTERVAL_MS = 66;  // about 15 Hz
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 10000;
constexpr char DEVICE_ID[] = "esp32_0";
constexpr char MOUNT[] = "right_gym_glove";

struct EulerAngles {
  float yaw;
  float pitch;
  float roll;
};

Adafruit_BNO08x bno08x(BNO08X_RESET);
sh2_SensorValue_t sensorValue;
WiFiUDP telemetryUdp;

float accelX = NAN;
float accelY = NAN;
float accelZ = NAN;
float gyroX = NAN;
float gyroY = NAN;
float gyroZ = NAN;
EulerAngles euler = {NAN, NAN, NAN};
unsigned long lastTelemetryMs = 0;
unsigned long lastWifiAttemptMs = 0;
uint32_t sequence = 0;
bool wifiConnectedLogged = false;
bool udpStarted = false;
bool dynamicDestinationReady = false;
IPAddress dynamicTelemetryDestinationIp;
uint16_t dynamicTelemetryDestinationPort = TELEMETRY_DESTINATION_PORT;

IPAddress telemetryDestinationIp() {
  if (dynamicDestinationReady) {
    return dynamicTelemetryDestinationIp;
  }
#if TELEMETRY_USE_BROADCAST
  return IPAddress(255, 255, 255, 255);
#else
  return TELEMETRY_DESTINATION_IP;
#endif
}

uint16_t telemetryDestinationPort() {
  return dynamicDestinationReady ? dynamicTelemetryDestinationPort : TELEMETRY_DESTINATION_PORT;
}

void formatFloat(char *buffer, size_t bufferSize, float value) {
  if (isnan(value) || isinf(value)) {
    snprintf(buffer, bufferSize, "null");
    return;
  }
  snprintf(buffer, bufferSize, "%.4f", value);
}

// SH2_GAME_ROTATION_VECTOR fuses accelerometer + gyroscope only (no
// magnetometer), so it has no compass reference: yaw is relative to wherever
// the sensor was pointed at power-on/reset and will drift slowly over a
// session. pitch/roll are gravity-referenced and stay accurate.
EulerAngles quaternionToEuler(float qr, float qi, float qj, float qk) {
  const float sqr = qr * qr;
  const float sqi = qi * qi;
  const float sqj = qj * qj;
  const float sqk = qk * qk;

  EulerAngles result;
  result.yaw = atan2f(2.0f * (qi * qj + qk * qr), (sqi - sqj - sqk + sqr)) * RAD_TO_DEG;
  result.pitch = asinf(-2.0f * (qi * qk - qj * qr) / (sqi + sqj + sqk + sqr)) * RAD_TO_DEG;
  result.roll = atan2f(2.0f * (qj * qk + qi * qr), (-sqi - sqj + sqk + sqr)) * RAD_TO_DEG;
  return result;
}

void setReports() {
  if (!bno08x.enableReport(SH2_ACCELEROMETER, 20000)) {
    Serial.println("{\"status\":\"error\",\"message\":\"could_not_enable_accelerometer\"}");
  }
  if (!bno08x.enableReport(SH2_GYROSCOPE_CALIBRATED, 20000)) {
    Serial.println("{\"status\":\"error\",\"message\":\"could_not_enable_gyroscope\"}");
  }
  if (!bno08x.enableReport(SH2_GAME_ROTATION_VECTOR, 20000)) {
    Serial.println("{\"status\":\"error\",\"message\":\"could_not_enable_game_rotation_vector\"}");
  }
}

bool beginBno08x() {
  delay(BNO08X_BOOT_DELAY_MS);

  for (uint8_t attempt = 1; attempt <= BNO08X_INIT_ATTEMPTS; attempt++) {
    if (bno08x.begin_I2C(BNO08X_I2C_ADDRESS, &Wire)) {
      Serial.printf(
          "{\"status\":\"imu_connected\",\"i2c_address\":\"0x%02X\",\"attempt\":%u}\n",
          BNO08X_I2C_ADDRESS,
          static_cast<unsigned int>(attempt));
      return true;
    }

    Serial.printf(
        "{\"status\":\"imu_retry\",\"i2c_address\":\"0x%02X\",\"attempt\":%u,\"max_attempts\":%u}\n",
        BNO08X_I2C_ADDRESS,
        static_cast<unsigned int>(attempt),
        static_cast<unsigned int>(BNO08X_INIT_ATTEMPTS));
    delay(BNO08X_INIT_RETRY_DELAY_MS);
  }

  return false;
}

void beginWiFiAttempt() {
  WiFi.mode(WIFI_STA);
  // Clear any stale connection state before retrying; reusing begin() alone
  // after a failed/dropped connection is a known source of ESP32 Wi-Fi
  // reconnect flakiness.
  WiFi.disconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttemptMs = millis();
  Serial.printf("{\"status\":\"wifi_connecting\",\"ssid\":\"%s\"}\n", WIFI_SSID);
}

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (udpStarted && wifiConnectedLogged) {
      return;
    }
    telemetryUdp.begin(LOCAL_UDP_PORT);
    udpStarted = true;
    wifiConnectedLogged = true;
    const IPAddress destinationIp = telemetryDestinationIp();
    Serial.printf(
        "{\"status\":\"wifi_connected\",\"ip\":\"%s\",\"udp_destination\":\"%s:%u\",\"broadcast\":%s}\n",
        WiFi.localIP().toString().c_str(),
        destinationIp.toString().c_str(),
        telemetryDestinationPort(),
        TELEMETRY_USE_BROADCAST ? "true" : "false");
    return;
  }

  if (wifiConnectedLogged) {
    Serial.println("{\"status\":\"wifi_disconnected\",\"message\":\"will_retry_without_blocking_imu\"}");
    wifiConnectedLogged = false;
    udpStarted = false;
    dynamicDestinationReady = false;
  }

  if (lastWifiAttemptMs == 0 || millis() - lastWifiAttemptMs >= WIFI_RETRY_INTERVAL_MS) {
    beginWiFiAttempt();
  }
}

void handleUdpDiscovery() {
  if (!udpStarted || WiFi.status() != WL_CONNECTED) {
    return;
  }

  int packetSize = telemetryUdp.parsePacket();
  while (packetSize > 0) {
    char packet[80];
    const int bytesRead = telemetryUdp.read(packet, sizeof(packet) - 1);
    packet[max(0, bytesRead)] = '\0';

    // Trim a trailing newline/carriage return so the token compares exactly.
    size_t packetLen = strlen(packet);
    while (packetLen > 0 && (packet[packetLen - 1] == '\n' || packet[packetLen - 1] == '\r')) {
      packet[--packetLen] = '\0';
    }

    // Require the shared token so a stray device on the same hotspot cannot
    // silently redirect the telemetry stream by sending its own discovery
    // packet. Expected format: "ironquest_discover:<DISCOVERY_TOKEN>".
    const char *marker = strstr(packet, "ironquest_discover:");
    if (marker != nullptr && strcmp(marker + strlen("ironquest_discover:"), DISCOVERY_TOKEN) == 0) {
      dynamicTelemetryDestinationIp = telemetryUdp.remoteIP();
      dynamicTelemetryDestinationPort = telemetryUdp.remotePort();
      dynamicDestinationReady = true;
      Serial.printf(
          "{\"status\":\"udp_peer_discovered\",\"ip\":\"%s\",\"port\":%u}\n",
          dynamicTelemetryDestinationIp.toString().c_str(),
          dynamicTelemetryDestinationPort);
    } else if (strstr(packet, "ironquest_discover") != nullptr) {
      Serial.println("{\"status\":\"udp_discovery_rejected\",\"message\":\"token_mismatch\"}");
    }

    packetSize = telemetryUdp.parsePacket();
  }
}

size_t buildTelemetryJson(char *buffer, size_t bufferSize) {
  char ax[16], ay[16], az[16], gx[16], gy[16], gz[16], pitch[16], roll[16], yaw[16];
  formatFloat(ax, sizeof(ax), accelX);
  formatFloat(ay, sizeof(ay), accelY);
  formatFloat(az, sizeof(az), accelZ);
  formatFloat(gx, sizeof(gx), gyroX);
  formatFloat(gy, sizeof(gy), gyroY);
  formatFloat(gz, sizeof(gz), gyroZ);
  formatFloat(pitch, sizeof(pitch), euler.pitch);
  formatFloat(roll, sizeof(roll), euler.roll);
  formatFloat(yaw, sizeof(yaw), euler.yaw);

  return snprintf(
      buffer,
      bufferSize,
      "{\"device_id\":\"%s\",\"timestamp_ms\":%lu,\"sequence\":%lu,\"mount\":\"%s\","
      "\"orientation_euler_deg\":{\"pitch\":%s,\"roll\":%s,\"yaw\":%s},"
      "\"accel_mps2\":{\"x\":%s,\"y\":%s,\"z\":%s},"
      "\"gyro_dps\":{\"x\":%s,\"y\":%s,\"z\":%s}}\n",
      DEVICE_ID,
      millis(),
      static_cast<unsigned long>(sequence++),
      MOUNT,
      pitch,
      roll,
      yaw,
      ax,
      ay,
      az,
      gx,
      gy,
      gz);
}

void publishTelemetry() {
  char payload[512];
  const size_t length = buildTelemetryJson(payload, sizeof(payload));
  const size_t payloadLength = min(length, sizeof(payload) - 1);
  Serial.print(payload);

  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  telemetryUdp.beginPacket(telemetryDestinationIp(), telemetryDestinationPort());
  telemetryUdp.write(reinterpret_cast<const uint8_t *>(payload), payloadLength);
  telemetryUdp.endPacket();
}

void setup() {
  Serial.begin(115200);

  const unsigned long serialWaitStartMs = millis();
  while (!Serial && millis() - serialWaitStartMs < 2000) {
  }

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  Serial.println("{\"status\":\"starting\",\"device\":\"esp32_s3_bno08x_udp\",\"i2c_address\":\"0x4B\"}");
  if (!beginBno08x()) {
    Serial.println("{\"status\":\"error\",\"message\":\"bno08x_not_found_at_0x4B\"}");
    while (true) {
      delay(1000);
    }
  }

  setReports();
  beginWiFiAttempt();
  Serial.println("{\"status\":\"ready\",\"device\":\"esp32_s3_bno08x_udp\"}");
}

void loop() {
  if (bno08x.wasReset()) {
    setReports();
  }

  maintainWiFi();
  handleUdpDiscovery();

  while (bno08x.getSensorEvent(&sensorValue)) {
    switch (sensorValue.sensorId) {
      case SH2_ACCELEROMETER:
        accelX = sensorValue.un.accelerometer.x;
        accelY = sensorValue.un.accelerometer.y;
        accelZ = sensorValue.un.accelerometer.z;
        break;
      case SH2_GYROSCOPE_CALIBRATED:
        gyroX = sensorValue.un.gyroscope.x * RAD_TO_DEG;
        gyroY = sensorValue.un.gyroscope.y * RAD_TO_DEG;
        gyroZ = sensorValue.un.gyroscope.z * RAD_TO_DEG;
        break;
      case SH2_GAME_ROTATION_VECTOR:
        euler = quaternionToEuler(
            sensorValue.un.gameRotationVector.real,
            sensorValue.un.gameRotationVector.i,
            sensorValue.un.gameRotationVector.j,
            sensorValue.un.gameRotationVector.k);
        break;
    }
  }

  const unsigned long nowMs = millis();
  if (nowMs - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = nowMs;
    publishTelemetry();
  }
}
