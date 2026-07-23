#include <Arduino.h>
#include <Wire.h>

constexpr int SDA_PIN = 8;
constexpr int SCL_PIN = 9;

void setup() {
  Serial.begin(115200);

  const unsigned long serialWaitStartMs = millis();
  while (!Serial && millis() - serialWaitStartMs < 2000) {
  }

  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.println();
  Serial.println("ESP32-S3 I2C scanner");
  Serial.printf("SDA = GPIO%d, SCL = GPIO%d\n", SDA_PIN, SCL_PIN);
}

void loop() {
  byte foundCount = 0;

  Serial.println("Scanning I2C bus...");
  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    const byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Found I2C device at 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.println(address, HEX);
      foundCount++;
    }
  }

  if (foundCount == 0) {
    Serial.println("No I2C devices found.");
  } else {
    Serial.printf("Done. Devices found: %d\n", foundCount);
  }

  Serial.println();
  delay(2000);
}
