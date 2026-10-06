# ESP32-S3 Biomechanical Keystroke Dynamics USB HID Keyboard
# ESP32-S3 智能拟人化击键动力学键盘系统

[English](#english) | [中文说明](#中文说明)

---

<a name="english"></a>
## English

An autonomous, full-stack human typing emulation and hardware keystroke injection system powered by **ESP32-S3 Native USB-OTG** and **Bluetooth Low Energy (BLE)**.

The system incorporates physiological biomechanics modeling, dual statistical distribution generators (Box-Muller Gaussian & Right-Skewed Log-Normal), and an asynchronous millisecond timeline event queue. It naturally replicates 2-Key Rollover (overlapping keystrokes during hand alternation), simulated human typos with backspace self-correction, and cognitive pauses, paired with a dedicated WeChat Mini Program for wireless long-text streaming and real-time control.

### System Architecture

```
esp32-keystroke-dynamics-keyboard/
├── esp32_firmware/         # ESP32-S3 Arduino hardware firmware
│   ├── esp32_firmware.ino  # Timeline engine, BLE GATT, Dell KB216 spoofing, HID reports
│   └── ble_controller.html # Backup Web Bluetooth controller interface
├── miniprogram/            # WeChat Mini Program controller (iOS / Android native)
│   ├── pages/index/        # Flow-controlled text chunking, preset switching, status logs
│   └── ...
├── 打字模型/ (typing_model) # Keystroke data engineering & biomechanical modeling
│   ├── collector.html      # Keystroke dynamics data collection web tool
│   ├── trainer.py          # Empirical parameter fitting and variance tuning
│   ├── user_profile.json   # Personalized biometrics from 507 real human keystrokes
│   └── ...
├── dynamics_engine.py      # Core Python keystroke dynamics algorithm prototype
├── simulator.py            # Terminal playback, histogram validation, and C++ header exporter
└── keyboard_layout.py      # QWERTY geometry, finger assignment, and hand mapping dictionary
```

### Key Features

1. **Hardware-Level USB Emulation & Zero-Footprint Stealth**
   - Native USB-OTG emulates a commercial **Dell KB216 Wired Keyboard** (`VID: 0x413C`, `PID: 0x2113`).
   - Disables startup USB CDC virtual serial port and DFU bootloader interfaces, completely hiding virtual COM ports from the operating system device tree.
   - Onboard status LEDs are disabled at the firmware level for completely dark, covert execution.

2. **Scheme 2: Asynchronous Event Timeline & 2-Key Rollover**
   - Eliminates legacy serial blocking delays (`press -> delay -> release`).
   - Chronological event scheduler (`TimelineEvent`) sorts `ACT_KEY_DOWN` and `ACT_KEY_UP` actions, naturally producing real human 2-Key Rollover (negative release-to-press latency during hand alternation).
   - Biomechanical constraints: strictly prevents key overlap on identical double letters and same-finger successive keys.
   - **Shift Lifecycle Isolation**: Shifts are scheduled with independent lead-in and lag-out buffers ($T_{\text{next\_down}} \ge T_{\text{shift\_up}} + 20\text{ms}$), completely eliminating modifier bleed and consecutive uppercase errors.
   - **HID Sanitization & Encoding Protection**: Clamps characters strictly to printable ASCII (32–126), automatically converts common Chinese full-width punctuation to ASCII equivalents, and blocks multi-byte high-order bytes (preventing byte `0xC1` from triggering `KEY_CAPS_LOCK`).

3. **Dual Statistical Distribution Generators**
   - **Dwell Time (Key Hold Duration)**: Box-Muller Gaussian distribution with variance tuned to human empirical baseline ($\sim 0.02\text{ s}^2$).
   - **Inter-Key Delay (Flight Time)**: Right-skewed Log-Normal distribution reflecting realistic human typing rhythms (frequent medium delays, rare ultra-short intervals, and an authentic heavy right tail).
   - Dynamic cognitive fatigue drift (random walk factor 0.86 ~ 1.18) and muscle memory acceleration on common Bigrams (35% speedup).

4. **Wireless BLE Streaming & WeChat Mini Program**
   - Negotiates 517-byte MTU with flow-controlled packet chunking (128-byte slices + 30ms queue drain delays) to prevent BLE GATT buffer deadlocks during 1300+ character continuous streams.
   - Dual-mode UTF-8 decoder (`TextDecoder` + URI percent encoding fallback) for garble-free real-time status telemetry.
   - Real-time pause/resume, emergency stop, and 5 adaptive biomechanical speed presets (22 ~ 70 WPM).

### Getting Started

#### 1. Firmware Upload (ESP32-S3)
1. Open `esp32_firmware/esp32_firmware.ino` in Arduino IDE.
2. Configure board options:
   - **Tools -> USB CDC On Boot**: `Disabled` (Essential: removes COM ports)
   - **Tools -> USB DFU On Boot**: `Disabled`
   - **Tools -> Upload Mode**: `UART0 / Hardware CDC`
   - **Tools -> USB Mode**: `Hardware CDC and JTAG` or `USB-OTG`
3. Download procedure: Hold **BOOT** button $\rightarrow$ click **RST** button once $\rightarrow$ release **BOOT** button to enter ROM download mode, then click **Upload** in Arduino IDE.

#### 2. WeChat Mini Program Setup
1. Open WeChat DevTools, click **Import Project**, and select the `miniprogram/` folder.
2. Select **Test Account (测试号)** for AppID, and click **Preview** to generate a QR code.
3. Scan the QR code using WeChat on iOS or Android, enable Bluetooth, and tap **一键连接 (One-Click Connect)**.

---

<a name="中文说明"></a>
## 中文说明

一套基于 **ESP32-S3 原生 USB-OTG** 与 **BLE 蓝牙** 的全栈拟人化击键仿真与无感硬件注入系统。

系统深度融合人类击键生物力学建模、双重统计学分布发生器（Box-Muller 正态分布与右偏对数正态分布）以及异步毫秒级时序事件队列。系统天然复现真实人手的 2-Key Rollover（双手交替时的按键物理重叠）、邻近键手滑打错与自动退格纠错、标点停顿，并配备专用的微信小程序进行无线长文本投送与双向实时控制。

### 系统架构

```
esp32-keystroke-dynamics-keyboard/
├── esp32_firmware/         # ESP32-S3 Arduino 硬件固件
│   ├── esp32_firmware.ino  # 核心固件：时序队列引擎、BLE GATT、Dell KB216 伪装、HID 报文控制
│   └── ble_controller.html # 备用 Web Bluetooth 控制器网页
├── miniprogram/            # 微信小程序端 (iOS / Android 原生支持)
│   ├── pages/index/        # 控制界面：长文本分包下发 (带防拥塞流控)、档位切换、硬件日志回传
│   └── ...
├── 打字模型/               # 击键动力学生物建模与数据工程
│   ├── collector.html      # 击键样本采集前端
│   ├── trainer.py          # 真实打字数据拟合与参数估计
│   ├── user_profile.json   # 507 次真实人手击键的个性化生物特征参数
│   └── ...
├── dynamics_engine.py      # Python 击键动力学核心算法原型
├── simulator.py            # 终端回放、统计直方图检验与数据导出工具
└── keyboard_layout.py      # QWERTY 键位生理力学、手指与手部映射字典
```

### 核心特性

1. **硬件级 USB 身份仿真与无感免驱**
   - 原生 USB-OTG 硬件伪装为 **Dell KB216 Wired Keyboard** (`VID: 0x413C`, `PID: 0x2113`)。
   - 彻底关闭启动挂载的 USB CDC 虚拟串口与 DFU 固件升级接口，在操作系统设备树中消除虚拟端口痕迹，完全呈现为单一纯物理键盘。
   - 硬件红色指示灯通过软件电平关断，纯黑无光隐蔽运行。

2. **方案 2：异步时序事件队列 (Event Timeline & 2-Key Rollover)**
   - 告别传统串行阻塞式的按压延迟（`press -> delay -> release`）。
   - 采用毫秒级时间戳排序调度列表（`TimelineEvent`），按先后顺序异步交织 `ACT_KEY_DOWN` 与 `ACT_KEY_UP`，天然呈现真人敲击时的“按键物理重叠 (2-Key Rollover)”；
   - 严格遵循生理力学约束：同键连续输入与同指连打严禁重叠，双手交替时高概率重叠。
   - **Shift 生命周期严格隔离**：Shift 前后延时独立调度，后续字母强制在 Shift 完全释放后触发（$T_{\text{next\_down}} \ge T_{\text{shift\_up}} + 20\text{ms}$），彻底根治修饰键渗漏与连环大写问题。
   - **HID 编码安全清洗**：严格限定 32~126 标准 ASCII 范围，自动转义常见全角/中文标点，杜绝 UTF-8 高位字节（如 `0xC1` 误触 `KEY_CAPS_LOCK`）对系统状态的破坏。

3. **双重统计学分布发生器**
   - **Dwell Time（按键保持时长）**：基于 Box-Muller 变换的高斯分布发生器，方差稳定在人类基准 `~0.02 s²`。
   - **Inter-Key Delay（键间飞行时间）**：采用右偏对数正态分布（Log-Normal Distribution），具备大量中等间隔、极少极短间隔与平滑的右偏长尾，完美通过击键动力学分布检验。
   - 动态疲劳漂移（Random Walk Drift）与 Bigram 肌肉记忆连击加速（35%）。

4. **BLE 跨端无线流式控制 (微信小程序)**
   - 协商 517 字节大 MTU，长文本流式分批分包下发（128 字节分块 + 30ms 队列排空延时），消除底层 GATT 缓冲区死锁，保障 1300+ 字符连续平稳传输。
   - 内建 UTF-8 多字节解码引擎（`TextDecoder` + URI Percent Fallback），保障硬件状态日志回传中文正常显示。
   - 支持实时暂停/继续、紧急中止与 5 档生物力学打字速率切换（22 ~ 70 WPM）。

### 快速上手

#### 1. 固件烧录 (ESP32-S3)
1. 使用 Arduino IDE 打开 `esp32_firmware/esp32_firmware.ino`。
2. 配置开发板菜单：
   - **Tools -> USB CDC On Boot** : `Disabled` (核心：彻底剥离虚拟串口)
   - **Tools -> USB DFU On Boot** : `Disabled`
   - **Tools -> Upload Mode** : `UART0 / Hardware CDC`
   - **Tools -> USB Mode** : `Hardware CDC and JTAG` 或 `USB-OTG`
3. 烧录方式（因已关闭 CDC）：按住板载 **BOOT** 键 $\rightarrow$ 轻按一下 **RST** 复位键 $\rightarrow$ 松开 **BOOT** 键进入硬件下载模式，在 IDE 点击 Upload 烧录。

#### 2. 小程序运行
1. 打开微信开发者工具，点击“导入项目”，目录选择 `miniprogram/`。
2. AppID 选择“测试号”即可，点击“预览”生成二维码用手机微信扫码运行。
3. 手机开启蓝牙，点击“一键连接”完成配对。

---

## 许可证 (License)

本项目采用 [MIT License](LICENSE) 授权。仅供技术交流与人机交互击键动力学仿真研究使用。
