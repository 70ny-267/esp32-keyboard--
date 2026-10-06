/**
 * ESP32-S3 智能击键键盘固件 (高阶防检测生物力学版 - 方案2: 异步时序事件队列引擎)
 * 
 * =========================================================================
 * 关键烧录设置 (Arduino IDE 菜单配置 - 彻底剥离虚拟串口与调试端口)
 * =========================================================================
 * 1. Tools -> USB CDC On Boot : 【Disabled】 (核心！关闭启动挂载虚拟串口，消除 COM 端口)
 * 2. Tools -> USB DFU On Boot : 【Disabled】 (关闭 DFU 固件升级接口)
 * 3. Tools -> Upload Mode     : 【UART0 / Hardware CDC】
 * 4. Tools -> USB Mode        : 【Hardware CDC and JTAG】或【USB-OTG (TinyUSB)】
 * 
 * 【重要重新烧录指南 (因关闭了 USB CDC)】：
 * 正常使用时，电脑设备管理器将只显示单一 Dell 键盘，不再暴露任何 COM 端口。
 * 下次如需更新固件，必须通过芯片硬件 ROM 引导模式连接：
 *   步骤：按住板载【BOOT】键 -> 轻按一下【RST】复位键 -> 松开【BOOT】键
 *   此时系统会临时识别到原生下载端口，在 Arduino IDE 点击 Upload 即可烧录。
 * =========================================================================
 * 
 * 核心生物识别与事件调度升级：
 * 1. 【方案2：时序事件队列 (Event Timeline & Key Overlap)】：
 *    - 彻底告别串行阻塞式的 press -> hold -> release；
 *    - 采用毫秒级时间戳排序调度列表，天然实现真人的“按键重叠 (2-Key Rollover)”；
 *    - 上一个键尚未松开时，下一个键已在 USB 报文中按下（负延迟负飞行时间）；
 *    - 严格遵循人手生理力学：同键连击（如 oo, tt）与同指连打（如 ed, rf）严禁重叠，双手交替时高概率重叠。
 * 2. 【Shift 异步分离】：Shift 按下超前 30~120ms，抬起滞后 20~55ms，独立事件调度。
 * 3. 【严格右偏对数正态分布 (Log-Normal Distribution)】：
 *    - 击键间隔 (IKD) 采用对数正态分布：大量中等间隔 (~180-220ms)，极少极短间隔 (>=35ms)，自然稀疏的极长停顿右偏长尾；
 *    - 彻底取代均匀随机与纯对称高斯分布，完美通过统计学分布检验。
 * 4. 模拟 Dell KB216 物理键盘 (VID: 0x413C, PID: 0x2113, Dell Inc.)。
 * 5. 软件强制熄灭 GPIO 48 板载红色指示灯 (输出高电平关断电流，纯黑无光运行)。
 * 6. 严格清洗非打印控制符（过滤 0x00~0x1F，杜绝 0x0C / FormFeed 误触 Ctrl+L 锁屏）。
 * 7. 支持 BLE 517 字节大 MTU，长文本流式分批调度，防止大文本截断。
 */

#include "USB.h"
#include "USBHIDKeyboard.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <math.h>
#include <vector>
#include <algorithm>

// ---------------- 方案2: 时序事件队列数据结构 ----------------
enum ActionType {
    ACT_KEY_DOWN = 0,
    ACT_KEY_UP   = 1
};

struct TimelineEvent {
    uint32_t timestamp_ms; // 绝对时间戳 (毫秒)
    uint8_t action;        // ACT_KEY_DOWN 或 ACT_KEY_UP
    uint8_t keycode;       // 键码 (支持物理字母/符号及 KEY_LEFT_SHIFT 等修饰键)
};

#define BOOT_BUTTON_PIN 0
#define RED_LED_PIN     48     // 板载红色指示灯 (GPIO 48)
#define DEVICE_NAME "AutoTyping-BLE"

#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

USBHIDKeyboard Keyboard;
BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

volatile bool isTyping = false;
volatile bool isPaused = false;
volatile bool stopRequested = false;

String pendingText = "";

// ---------------- 5 档独立防检测速率预设 ----------------
struct SpeedPreset {
    const char* name;
    float flight_median; // 键间飞行间隔中位数 (ms)
    float dwell_mean;    // 按键物理按下保持时长均值 (ms)
    float dwell_std;     // 按键保持标准差 (ms) -> 决定真实方差 (~140ms -> (0.14s)^2 ≈ 0.02)
    float dwell_min;     // 物理安全底线 (ms)
    float space_pause;   // 空格停顿中位数 (ms)
    float punct_pause;   // 标点思考停顿中位数 (ms)
    float typo_rate;     // 手误率
};

const SpeedPreset PRESETS[5] = {
    // 0: 我的专属节奏 (完全基于你 507 次最新采样生物特征: 34.6 WPM, Dwell 方差调校至 ~0.02 s^2)
    {"我的专属", 255.5, 95.1, 140.0, 50.0, 334.4, 512.4, 0.020},
    // 1: 沉稳严谨 (~22 WPM)
    {"沉稳严谨", 320.0, 92.0, 130.0, 50.0, 450.0, 380.0, 0.008},
    // 2: 日常自然 (~38 WPM)
    {"日常自然", 190.0, 85.0, 110.0, 45.0, 320.0, 280.0, 0.015},
    // 3: 流畅熟练 (~52 WPM)
    {"流畅熟练", 130.0, 78.0, 95.0,  40.0, 220.0, 200.0, 0.022},
    // 4: 极速爆发 (~70 WPM)
    {"极速爆发", 90.0,  70.0, 80.0,  40.0, 160.0, 150.0, 0.028}
};

// 显式函数前向声明 (避免 Arduino 自动生成的原型因位置早于结构体导致编译报错)
void buildTimelineForChunk(const String &chunk, const SpeedPreset &p, std::vector<TimelineEvent> &timeline);
void executeTimeline(const std::vector<TimelineEvent> &timeline);

int currentPresetIndex = 0; // 默认使用“我的专属节奏”
float driftFactor = 1.0;    // 动态疲劳漂移因子
int typedCharCount = 0;

// 常见肌肉记忆连词 (Fast Bigrams)
const char* FAST_BIGRAMS[] = {
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
    "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
    "st", "to", "nt", "ng", "se", "ha", "as", "ou", "io", "le",
    "ve", "co", "me", "de", "hi", "ri", "ro", "ic", "ne", "ea", "fo"
};
const int FAST_BIGRAMS_COUNT = 41;

bool isFastBigram(char c1, char c2) {
    char b[3] = {(char)tolower(c1), (char)tolower(c2), '\0'};
    for (int i = 0; i < FAST_BIGRAMS_COUNT; i++) {
        if (strcmp(b, FAST_BIGRAMS[i]) == 0) return true;
    }
    return false;
}

// 物理邻近键映射 (用于真实手滑模拟)
char getAdjacentKey(char c) {
    c = tolower(c);
    switch (c) {
        case 'q': return (random(0,2) ? 'w' : 'a');
        case 'w': return (random(0,2) ? 'e' : 's');
        case 'e': return (random(0,2) ? 'r' : 'd');
        case 'r': return (random(0,2) ? 't' : 'f');
        case 't': return (random(0,2) ? 'y' : 'g');
        case 'y': return (random(0,2) ? 'u' : 'h');
        case 'u': return (random(0,2) ? 'i' : 'j');
        case 'i': return (random(0,2) ? 'o' : 'k');
        case 'o': return (random(0,2) ? 'p' : 'l');
        case 'p': return (random(0,2) ? 'o' : ';');
        case 'a': return (random(0,2) ? 's' : 'q');
        case 's': return (random(0,2) ? 'd' : 'w');
        case 'd': return (random(0,2) ? 'f' : 'e');
        case 'f': return (random(0,2) ? 'g' : 'r');
        case 'g': return (random(0,2) ? 'h' : 't');
        case 'h': return (random(0,2) ? 'j' : 'y');
        case 'j': return (random(0,2) ? 'k' : 'u');
        case 'k': return (random(0,2) ? 'l' : 'i');
        case 'l': return (random(0,2) ? ';' : 'o');
        case 'z': return (random(0,2) ? 'x' : 'a');
        case 'x': return (random(0,2) ? 'c' : 's');
        case 'c': return (random(0,2) ? 'v' : 'd');
        case 'v': return (random(0,2) ? 'b' : 'f');
        case 'b': return (random(0,2) ? 'n' : 'g');
        case 'n': return (random(0,2) ? 'm' : 'h');
        case 'm': return (random(0,2) ? 'n' : 'j');
        default: return (c == 'z' ? 'a' : c + 1);
    }
}

// 过滤不可见的危险控制符与非 ASCII 字符（严格限制在 32~126，避免意外触发 0xC1 Caps Lock 或系统热键）
bool isSafePrintableChar(char c) {
    if (c == '\n' || c == '\t') return true;
    unsigned char uc = (unsigned char)c;
    // 严格限制在标准可打印 ASCII 范围 (32 ~ 126)
    // 必须拦截所有 >= 127 的高位字节：
    // 在 Arduino ESP32 USBHIDKeyboard.h 中，0xC1(193) 为 KEY_CAPS_LOCK，0x81 为 KEY_LEFT_SHIFT 等，
    // 若 UTF-8 多字节序列穿透到 Keyboard.press()，遇到 0xC1 字节会直接触发物理 Caps Lock 锁定！
    if (uc >= 32 && uc <= 126) return true;
    return false;
}

// ---------------- 生物力学属性：左右手与手指映射 ----------------
char getHand(char c) {
    c = tolower(c);
    const char* leftKeys = "12345qwertasdfgzxcvb!@#$%QWERTASDFGZXCVB";
    if (strchr(leftKeys, c) != NULL) return 'L';
    return 'R';
}

uint8_t getFinger(char c) {
    c = tolower(c);
    // 1=小指, 2=无名指, 3=中指, 4=食指
    switch (c) {
        case 'q': case 'a': case 'z': case '1': case 'p': case ';': case '/': case '0': return 1;
        case 'w': case 's': case 'x': case '2': case 'o': case 'l': case '.': case '9': return 2;
        case 'e': case 'd': case 'c': case '3': case 'i': case 'k': case ',': case '8': return 3;
        case 'r': case 't': case 'f': case 'g': case 'v': case 'b': case '4': case '5':
        case 'y': case 'u': case 'h': case 'j': case 'n': case 'm': case '6': case '7': return 4;
        default: return 0;
    }
}

// ---------------- 数学分布发生器 ----------------

// 1. 高斯/正态分布发生器 (Box-Muller 算法) - 用于 Dwell 按键保持时长
float sampleGaussian(float mean, float stdDev) {
    float u1 = (float)random(1, 10000) / 10000.0;
    float u2 = (float)random(1, 10000) / 10000.0;
    float z0 = sqrt(-2.0 * log(u1)) * cos(2.0 * 3.1415926535 * u2);
    return mean + z0 * stdDev;
}

// 2. 右偏对数正态分布 (Log-Normal Distribution) 发生器 - 用于 IKD 键间飞行时间
// medianTarget: 中位数目标 (例如 ~200ms)
// sigma: 形状参数 (0.35~0.42，形成符合真实人类击键的平滑右偏长尾)
float sampleLogNormal(float medianTarget, float sigma) {
    float u1 = (float)random(1, 10000) / 10000.0;
    float u2 = (float)random(1, 10000) / 10000.0;
    float z = sqrt(-2.0 * log(u1)) * cos(2.0 * 3.1415926535 * u2);
    float val = medianTarget * exp(sigma * z);

    // 物理生理极限保护
    if (val < 32.0) val = 32.0;       // 机械键轴弹起物理极值
    if (val > 1500.0) val = 1500.0;   // 避免长尾极端过长
    return val;
}

// ---------------- 解析 Shift 物理基准键 ----------------
char getBaseKey(char c, bool &needShift) {
    needShift = false;
    if (c >= 'A' && c <= 'Z') {
        needShift = true;
        return (char)tolower(c);
    }
    switch (c) {
        case '!': needShift = true; return '1';
        case '@': needShift = true; return '2';
        case '#': needShift = true; return '3';
        case '$': needShift = true; return '4';
        case '%': needShift = true; return '5';
        case '^': needShift = true; return '6';
        case '&': needShift = true; return '7';
        case '*': needShift = true; return '8';
        case '(': needShift = true; return '9';
        case ')': needShift = true; return '0';
        case '_': needShift = true; return '-';
        case '+': needShift = true; return '=';
        case '{': needShift = true; return '[';
        case '}': needShift = true; return ']';
        case '|': needShift = true; return '\\';
        case ':': needShift = true; return ';';
        case '"': needShift = true; return '\'';
        case '<': needShift = true; return ',';
        case '>': needShift = true; return '.';
        case '?': needShift = true; return '/';
        case '~': needShift = true; return '`';
        default: return c;
    }
}

// ---------------- 方案2: 核心时序时间线发生器与执行器 ----------------

void sendBleNotify(const String &msg) {
    if (deviceConnected && pTxCharacteristic != NULL) {
        pTxCharacteristic->setValue((uint8_t*)msg.c_str(), msg.length());
        pTxCharacteristic->notify();
    }
}

void togglePause(const char *source) {
    if (!isTyping) return;
    isPaused = !isPaused;
    if (isPaused) {
        Keyboard.releaseAll();
        sendBleNotify(String("[状态: 已暂停 (来自 ") + source + ")]");
    } else {
        sendBleNotify(String("[状态: 继续打字 (来自 ") + source + ")]");
    }
}

void requestStop() {
    stopRequested = true;
    isPaused = false;
    Keyboard.releaseAll();
    sendBleNotify("[状态: 打字已中止]");
}

void checkBootButton() {
    static int lastState = HIGH;
    int curState = digitalRead(BOOT_BUTTON_PIN);
    if (lastState == HIGH && curState == LOW) {
        delay(25);
        if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
            togglePause("板载BOOT键");
            while (digitalRead(BOOT_BUTTON_PIN) == LOW) {
                delay(10);
            }
        }
    }
    lastState = curState;
}

// ---------------- 方案2: 核心时序时间线发生器与执行器 ----------------

/**
 * 针对一段文本生成物理按键事件时间线 (支持 2-Key Rollover 重叠与 Shift 异步解耦)
 */
void buildTimelineForChunk(const String &chunk, const SpeedPreset &p, std::vector<TimelineEvent> &timeline) {
    timeline.clear();
    timeline.reserve(chunk.length() * 4);

    uint32_t t_current_press = 50; // 起始基准偏移
    char prev_c = 0;
    float prev_dwell = 90.0;
    uint32_t prev_key_up = 0;
    uint32_t last_shift_up = 0;
    bool prev_had_shift = false;

    for (size_t i = 0; i < chunk.length(); i++) {
        char c = chunk[i];

        // 1. 低频随机游走漂移 (疲劳/注意力波动)
        typedCharCount++;
        if (typedCharCount % 12 == 0) {
            driftFactor += ((float)random(-5, 6) / 100.0);
            if (driftFactor < 0.86) driftFactor = 0.86;
            if (driftFactor > 1.18) driftFactor = 1.18;
        }

        // 2. 多态手误注入 (若触发则在目标按键前插入手误事件与退格事件)
        if (p.typo_rate > 0 && isalpha(c) && ((float)random(0, 1000) / 1000.0) < p.typo_rate) {
            char wrong_c = getAdjacentKey(c);
            bool wrongShift = false;
            char wrongBase = getBaseKey(wrong_c, wrongShift);

            float wrongDwell = sampleGaussian(p.dwell_mean, p.dwell_std);
            if (wrongDwell < p.dwell_min) wrongDwell = p.dwell_min;

            uint32_t t_wrong_down = t_current_press + (uint32_t)sampleLogNormal(p.flight_median * 0.9 * driftFactor, 0.35);
            uint32_t t_wrong_up = t_wrong_down + (uint32_t)wrongDwell;

            timeline.push_back({t_wrong_down, ACT_KEY_DOWN, (uint8_t)wrongBase});
            timeline.push_back({t_wrong_up,   ACT_KEY_UP,   (uint8_t)wrongBase});

            // 生理反应思考时间 (180 ~ 280ms)
            uint32_t t_bs_down = t_wrong_up + (uint32_t)random(180, 280);
            float bsDwell = sampleGaussian(p.dwell_mean * 0.8, 20.0);
            if (bsDwell < 45.0) bsDwell = 45.0;
            uint32_t t_bs_up = t_bs_down + (uint32_t)bsDwell;

            timeline.push_back({t_bs_down, ACT_KEY_DOWN, (uint8_t)KEY_BACKSPACE});
            timeline.push_back({t_bs_up,   ACT_KEY_UP,   (uint8_t)KEY_BACKSPACE});

            // 退格完成后重新定位
            t_current_press = t_bs_up + (uint32_t)random(90, 160);
            prev_dwell = bsDwell;
            prev_key_up = t_bs_up;
            prev_c = 0;
            prev_had_shift = false;
        }

        // 3. 计算当前字符的 Dwell (按键保持时长 - 高斯分布，方差 ~0.02)
        float dwell = sampleGaussian(p.dwell_mean, p.dwell_std);
        if (c == ' ') dwell += 15.0;
        if (dwell < p.dwell_min) dwell = p.dwell_min;
        if (dwell > 380.0) dwell = 380.0;

        // 4. 计算当前字符与前一字符的按压间隔 IKD (Inter-Key Delay - 右偏对数正态分布)
        float ikdMedian = p.flight_median * driftFactor;
        if (prev_c == ' ') {
            ikdMedian = p.space_pause * driftFactor;
        } else if (prev_c == '.' || prev_c == '!' || prev_c == '?' || prev_c == '\n') {
            ikdMedian = p.punct_pause * 1.5 * driftFactor;
        } else if (prev_c == ',' || prev_c == ';' || prev_c == ':') {
            ikdMedian = p.punct_pause * driftFactor;
        } else if (isFastBigram(prev_c, c)) {
            ikdMedian *= 0.65; // 肌肉记忆连键加速 35%
        }

        // 右偏对数正态采样：集中在 ~200ms，极少极短间隔，具备平滑右偏长尾
        float ikd = sampleLogNormal(ikdMedian, 0.36);

        // 5. 生理力学约束与按键重叠 (Key Overlap) 裁决
        char h1 = getHand(prev_c);
        char h2 = getHand(c);
        uint8_t f1 = getFinger(prev_c);
        uint8_t f2 = getFinger(c);

        if (prev_c == c) {
            // 同一按键连续输入：物理键轴不可能在前一次抬起前再次触发，严禁重叠！
            if (ikd < prev_dwell + 40.0) {
                ikd = prev_dwell + (float)random(35, 65);
            }
        } else if (h1 == h2 && f1 == f2 && f1 != 0) {
            // 同一只手的同一根手指连打 (如 ed, rf)：手指不可能同时按两键，严禁重叠！
            if (ikd < prev_dwell + 25.0) {
                ikd = prev_dwell + (float)random(25, 50);
            }
        } else if (h1 != h2 && prev_c != 0) {
            // 双手交替击键 (如 th, er, on)：另一只手已提前就位，高概率产生物理按键重叠！
            ikd *= 0.72; // 交替加速，天然使得 ikd < prev_dwell，发生 20~55ms 的 Rollover 真实重叠
            if (ikd < 36.0) ikd = 36.0;
        } else {
            // 同手不同指
            if (ikd < 45.0) ikd = 45.0;
        }

        // 计算当前键绝对下压时间
        t_current_press += (uint32_t)ikd;

        // 6. 解析 Shift 与按键事件排布
        bool needShift = false;
        char baseKey = getBaseKey(c, needShift);

        // 【关键保护1】：若前一个字符使用了 Shift，当前字符的下压时间必须严格在 Shift 完全释放之后！
        // 杜绝 2-Key Rollover 导致下一个小写字母下压时 Shift 尚未释放，从而造成连环大写 (如 The -> THE)
        if (prev_had_shift) {
            if (t_current_press < last_shift_up + 20) {
                t_current_press = last_shift_up + (uint32_t)random(20, 45);
            }
        }

        if (needShift) {
            // Shift 异步时序：先按下 Shift -> 延迟 25~50ms -> 按下基准键 -> 释放基准键 -> 滞后 18~35ms -> 释放 Shift
            uint32_t t_shift_pre = (uint32_t)random(25, 55);
            uint32_t t_shift_down = (t_current_press > t_shift_pre) ? (t_current_press - t_shift_pre) : 0;

            // 【关键保护2】：Shift 下压不能早于上一个键的完全抬起，避免修饰键渗漏给上一个普通键
            if (prev_c != 0 && t_shift_down < prev_key_up + 10) {
                t_shift_down = prev_key_up + 10;
                if (t_current_press <= t_shift_down) {
                    t_current_press = t_shift_down + (uint32_t)random(15, 30);
                }
            }

            uint32_t t_key_down = t_current_press;
            uint32_t t_key_up   = t_key_down + (uint32_t)dwell;
            uint32_t t_shift_up = t_key_up + (uint32_t)random(18, 38);

            timeline.push_back({t_shift_down, ACT_KEY_DOWN, (uint8_t)KEY_LEFT_SHIFT});
            timeline.push_back({t_key_down,   ACT_KEY_DOWN, (uint8_t)baseKey});
            timeline.push_back({t_key_up,     ACT_KEY_UP,   (uint8_t)baseKey});
            timeline.push_back({t_shift_up,   ACT_KEY_UP,   (uint8_t)KEY_LEFT_SHIFT});

            prev_key_up = t_key_up;
            last_shift_up = t_shift_up;
            prev_had_shift = true;
        } else {
            uint32_t t_key_down = t_current_press;
            uint32_t t_key_up   = t_key_down + (uint32_t)dwell;

            timeline.push_back({t_key_down, ACT_KEY_DOWN, (uint8_t)c});
            timeline.push_back({t_key_up,   ACT_KEY_UP,   (uint8_t)c});

            prev_key_up = t_key_up;
            prev_had_shift = false;
        }

        prev_dwell = dwell;
        prev_c = c;
    }

    // 核心步骤：按照绝对时间戳排序时间线，重叠事件将按物理真实先后自然交织！
    std::stable_sort(timeline.begin(), timeline.end(), [](const TimelineEvent &a, const TimelineEvent &b) {
        return a.timestamp_ms < b.timestamp_ms;
    });
}

/**
 * 方案2执行器：按绝对时间戳时钟驱动消费事件时间线
 */
void executeTimeline(const std::vector<TimelineEvent> &timeline) {
    uint32_t t_last = 0;

    for (size_t i = 0; i < timeline.size(); i++) {
        if (stopRequested) {
            Keyboard.releaseAll();
            break;
        }

        uint32_t t_target = timeline[i].timestamp_ms;
        if (t_target > t_last) {
            uint32_t wait_ms = t_target - t_last;
            uint32_t start_w = millis();

            // 切片可中断微延时
            while (millis() - start_w < wait_ms) {
                if (stopRequested) {
                    Keyboard.releaseAll();
                    break;
                }
                while (isPaused) {
                    if (stopRequested) {
                        Keyboard.releaseAll();
                        break;
                    }
                    checkBootButton();
                    delay(30);
                }
                checkBootButton();
                uint32_t elapsed = millis() - start_w;
                if (elapsed >= wait_ms) break;
                uint32_t rem = wait_ms - elapsed;
                delay(rem > 8 ? 8 : rem);
            }
        }

        if (stopRequested) {
            Keyboard.releaseAll();
            break;
        }

        // 发送对应 HID 动作
        if (timeline[i].action == ACT_KEY_DOWN) {
            Keyboard.press(timeline[i].keycode);
        } else {
            Keyboard.release(timeline[i].keycode);
        }

        t_last = t_target;
    }

    // 单批次结束确保无物理粘键
    Keyboard.releaseAll();
}

// ---------------- 蓝牙回调逻辑 ----------------
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        deviceConnected = true;
    }
    void onDisconnect(BLEServer* pServer) {
        deviceConnected = false;
    }
};

class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
        String rxValue = String(pCharacteristic->getValue().c_str());
        if (rxValue.length() == 0) return;

        // 指令判断
        if (rxValue.equalsIgnoreCase("pause") || rxValue.equalsIgnoreCase("p")) {
            togglePause("手机蓝牙");
            return;
        } 
        if (rxValue.equalsIgnoreCase("resume") || rxValue.equalsIgnoreCase("r")) {
            if (isPaused) togglePause("手机蓝牙");
            return;
        } 
        if (rxValue.equalsIgnoreCase("stop") || rxValue.equalsIgnoreCase("s")) {
            requestStop();
            return;
        } 

        // 切换档位指令 [P:0] ~ [P:4]
        if (rxValue.startsWith("[P:") && rxValue.endsWith("]")) {
            int pIdx = rxValue.substring(3, rxValue.length() - 1).toInt();
            if (pIdx >= 0 && pIdx <= 4) {
                currentPresetIndex = pIdx;
                String msg = String("[档位切换: ") + PRESETS[currentPresetIndex].name + "]";
                sendBleNotify(msg);
            }
            return;
        }

        // 正文直发追加
        pendingText += rxValue;
    }
};

void setup() {
    // 强制彻底关闭板载 48 号红色指示灯 (低电平点亮，设置为高电平 HIGH 切断电流关断)
    pinMode(RED_LED_PIN, OUTPUT);
    digitalWrite(RED_LED_PIN, HIGH);
    neopixelWrite(RED_LED_PIN, 0, 0, 0); // 确保若是 RGB 灯珠也熄灭全黑

    pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);

    // -------- 硬件级 USB 身份伪装 (Dell KB216) --------
    USB.VID(0x413C);                              // Dell Vendor ID
    USB.PID(0x2113);                              // Dell KB216 Product ID
    USB.productName("Dell KB216 Wired Keyboard"); // 硬件产品名称
    USB.manufacturerName("Dell");                 // 硬件厂商名称
    USB.serialNumber("CN016MD071616");            // 仿真商业序列号

    Keyboard.begin();
    USB.begin();
    Keyboard.releaseAll(); // 确保开机即处于干净的零报文状态，清除任何悬空修饰键，杜绝上电 Caps Lock 残留

    // -------- 蓝牙 BLE 服务初始化 (配置 517 MTU 防止大文本截断) --------
    BLEDevice::init(DEVICE_NAME);
    BLEDevice::setMTU(517); // 升级蓝牙协议栈支持大包吞吐

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    BLEService *pService = pServer->createService(SERVICE_UUID);

    pTxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_TX,
        BLECharacteristic::PROPERTY_NOTIFY
    );
    pTxCharacteristic->addDescriptor(new BLE2902());

    BLECharacteristic *pRxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_RX,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
    );
    pRxCharacteristic->setCallbacks(new MyCallbacks());

    pService->start();

    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->setMinPreferred(0x12);
    BLEDevice::startAdvertising();
}

void loop() {
    if (pendingText.length() > 0 && !isTyping) {
        // 延时等待一段让首批分包充分进入缓冲池
        delay(120);
        String textToType = pendingText;
        pendingText = "";
        isTyping = true;
        stopRequested = false;

        const SpeedPreset &curPreset = PRESETS[currentPresetIndex];
        sendBleNotify(String("[开始输入: ") + textToType.length() + " 字符 | 模式: " + curPreset.name + "]");
        
        // 2秒倒计时给用户切换输入窗口
        for (int i = 0; i < 20; i++) {
            if (stopRequested) break;
            checkBootButton();
            delay(100);
        }
        Keyboard.releaseAll(); // 开始输入前确保键位与修饰键完全清空

        // 预处理常见 UTF-8 中文/全角标点符号替换为 ASCII 对应字符，防止漏打标点
        textToType.replace("，", ",");
        textToType.replace("。", ".");
        textToType.replace("！", "!");
        textToType.replace("？", "?");
        textToType.replace("：", ":");
        textToType.replace("；", ";");
        textToType.replace("“", "\"");
        textToType.replace("”", "\"");
        textToType.replace("‘", "'");
        textToType.replace("’", "'");
        textToType.replace("（", "(");
        textToType.replace("）", ")");
        textToType.replace("【", "[");
        textToType.replace("】", "]");
        textToType.replace("、", ",");
        textToType.replace("——", "--");
        textToType.replace("—", "-");
        textToType.replace("～", "~");
        textToType.replace("　", " "); // 全角空格

        // 清洗非法控制字符并严格限制在 ASCII 32~126
        String sanitizedText = "";
        sanitizedText.reserve(textToType.length());
        for (size_t i = 0; i < textToType.length(); i++) {
            char c = textToType[i];
            if (c == '\r') continue;
            if (isSafePrintableChar(c)) sanitizedText += c;
        }

        // 按人类认知自然分段 (每 200~300 字符为一批次生成时序事件队列，并在段尾触发自然审稿停顿)
        size_t offset = 0;
        std::vector<TimelineEvent> timeline;

        while (offset < sanitizedText.length() && !stopRequested) {
            // 动态截取 200~300 字符到最近的单词/标点边界
            size_t chunkSize = random(200, 300);
            if (offset + chunkSize >= sanitizedText.length()) {
                chunkSize = sanitizedText.length() - offset;
            } else {
                // 寻找自然词尾/句尾断句
                size_t lookahead = chunkSize;
                while (offset + lookahead < sanitizedText.length() && lookahead < chunkSize + 60) {
                    char bc = sanitizedText[offset + lookahead];
                    if (bc == ' ' || bc == '.' || bc == ',' || bc == '\n') {
                        lookahead++;
                        break;
                    }
                    lookahead++;
                }
                chunkSize = lookahead;
            }

            String chunk = sanitizedText.substring(offset, offset + chunkSize);
            offset += chunkSize;

            // 1. 生成并调度本段的时序事件队列 (带 2-Key Rollover 重叠与对数正态分布)
            buildTimelineForChunk(chunk, curPreset, timeline);

            // 2. 执行时间线
            executeTimeline(timeline);

            // 3. 自然长文本审稿停顿 (若还有未完文本)
            if (offset < sanitizedText.length() && !stopRequested) {
                float reviewSec = (float)random(42, 75) / 10.0; // 4.2s ~ 7.5s
                sendBleNotify(String("[审稿休息中: 停顿 ") + String(reviewSec, 1) + "秒]");

                uint32_t rStart = millis();
                uint32_t rDuration = (uint32_t)(reviewSec * 1000.0);
                while (millis() - rStart < rDuration) {
                    if (stopRequested) break;
                    while (isPaused) {
                        if (stopRequested) break;
                        checkBootButton();
                        delay(40);
                    }
                    checkBootButton();
                    delay(15);
                }
            }
        }

        if (!stopRequested) {
            sendBleNotify("[打字全部完成！]");
        }

        isTyping = false;
        isPaused = false;
        stopRequested = false;
    }

    checkBootButton();

    if (!deviceConnected && oldDeviceConnected) {
        delay(500);
        pServer->startAdvertising();
        oldDeviceConnected = deviceConnected;
    }
    if (deviceConnected && !oldDeviceConnected) {
        oldDeviceConnected = deviceConnected;
    }

    delay(10);
}
