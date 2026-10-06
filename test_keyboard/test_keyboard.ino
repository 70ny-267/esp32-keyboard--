/**
 * 极简硬件打字测试 (无需蓝牙、无需小程序、纯硬件验证)
 * 作用：验证你的 ESP32-S3 是否能作为物理键盘向 Mac 输入字符
 * 
 * 表现：
 * 烧录完成后，每隔 3 秒钟会自动在电脑上打出一个字母 'a'
 */

#include "USB.h"
#include "USBHIDKeyboard.h"

USBHIDKeyboard Keyboard;

void setup() {
  Keyboard.begin();
  USB.begin();
}

void loop() {
  delay(3000);
  Keyboard.print("a");
}
