// Auto-generated Keystroke Dynamics Data for ESP32-S3
#pragma once
#include <stdint.h>

struct KeyAction {
    char c;
    uint8_t shift;
    uint16_t flight_ms;
    uint16_t dwell_ms;
    uint8_t is_bs;
};

const int KEY_ACTIONS_COUNT = 18;
const KeyAction PROGMEM KEY_ACTIONS[] = {
    {'H', 1, 172, 111, 0},
    {'e', 0, 51, 99, 0},
    {'l', 0, 61, 63, 0},
    {'l', 0, 108, 101, 0},
    {'o', 0, 105, 89, 0},
    {' ', 0, 70, 103, 0},
    {'3', 0, 82, 66, 0},
    {'\b', 0, 228, 86, 1},
    {'W', 1, 154, 91, 0},
    {'o', 0, 95, 89, 0},
    {'r', 0, 55, 101, 0},
    {';', 0, 92, 72, 0},
    {'\b', 0, 313, 97, 1},
    {'l', 0, 127, 70, 0},
    {'c', 0, 70, 82, 0},
    {'\b', 0, 230, 90, 1},
    {'d', 0, 121, 107, 0},
    {'!', 1, 37, 65, 0},
};
