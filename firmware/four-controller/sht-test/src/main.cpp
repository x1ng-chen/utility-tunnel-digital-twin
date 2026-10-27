/*
 * 临时 SHT 模块测试：SDA=GPIO4，SCL=GPIO5。
 * 上电扫描 I2C 总线并尝试读取 0x44 / 0x45 的温度湿度原始值，串口 115200 输出。
 */
#include <Arduino.h>
#include <Wire.h>

static uint8_t crc8(const uint8_t *data, size_t len)
{
  uint8_t crc = 0xFF;
  for (size_t i = 0; i < len; ++i)
  {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; ++b)
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
  }
  return crc;
}

static void try_read(uint8_t address)
{
  Wire.beginTransmission(address);
  Wire.write(0x24);
  Wire.write(0x00);
  uint8_t err = Wire.endTransmission();
  if (err != 0)
  {
    Serial.printf("ADDR 0x%02X write_cmd_err=%u\n", address, err);
    return;
  }
  delay(50);
  uint8_t got = Wire.requestFrom((int)address, 6);
  uint8_t data[6] = {0};
  for (uint8_t i = 0; i < got && i < 6; ++i) data[i] = (uint8_t)Wire.read();
  Serial.printf("ADDR 0x%02X got=%u raw=%02X %02X %02X %02X %02X %02X crcT=%s crcH=%s\n",
                address, got, data[0], data[1], data[2], data[3], data[4], data[5],
                (crc8(data, 2) == data[2]) ? "OK" : "BAD",
                (crc8(&data[3], 2) == data[5]) ? "OK" : "BAD");
  if (got == 6 && crc8(data, 2) == data[2])
  {
    uint16_t raw_t = ((uint16_t)data[0] << 8) | data[1];
    uint16_t raw_h = ((uint16_t)data[3] << 8) | data[4];
    Serial.printf("  T=%.2fC  H=%.2f%%\n",
                  -45.0 + 175.0 * raw_t / 65535.0,
                  100.0 * raw_h / 65535.0);
  }
}

static void scan_bus(uint8_t sda, uint8_t scl)
{
  Wire.begin(sda, scl);
  Wire.setClock(100000);
  delay(100);
  Serial.printf("SCAN SDA=%u SCL=%u\n", sda, scl);
  for (uint8_t addr = 1; addr < 127; ++addr)
  {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) Serial.printf("FOUND 0x%02X\n", addr);
  }
  try_read(0x44);
  try_read(0x45);
}

void setup()
{
  Serial.begin(115200);
  delay(500);
  Serial.println("SHT_TEST");
  scan_bus(4, 5);   /* SDA=4 SCL=5 */
  delay(300);
  scan_bus(5, 4);   /* 对调 */
}

void loop()
{
  delay(5000);
  scan_bus(4, 5);
  delay(200);
  scan_bus(5, 4);
}
