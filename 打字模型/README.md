# 个人打字生物特征建模工具 (Personal Keystroke Dynamics)

本模块用于采集你真实的击键时序数据，训练属于你的个性化击键生物特征模型（`user_profile.json`），并驱动模拟器/ESP32 硬件以你的自然节奏输出。

## 文件组成

- [collector.py](file:///Users/mac/开发/自动键盘/打字模型/collector.py)：本地轻量级 Web 数据采集服务端，自动打开浏览器进行高精度时序采集。
- [collector.html](file:///Users/mac/开发/自动键盘/打字模型/collector.html)：前端采集页面，利用浏览器 `performance.now()` 实现微秒级按下（Dwell）与间隔（Flight）捕获。
- [trainer.py](file:///Users/mac/开发/自动键盘/打字模型/trainer.py)：特征提取与指纹拟合器，提取专属 Dwell 分布、双键组合（Bigram）肌肉记忆、空格词间停顿与思考停顿。
- [personalized_simulator.py](file:///Users/mac/开发/自动键盘/打字模型/personalized_simulator.py)：加载你训练好的模型文件，对任意输入文本进行高拟真回放或导出给硬件。

## 使用流程

### 第一步：启动采集器并打字
在终端运行：
```bash
cd /Users/mac/开发/自动键盘/打字模型
python3 collector.py
```
* 系统会自动在浏览器中弹出采集页面（`http://127.0.0.1:8765`）。
* 在输入框内用你平常的自然节奏打字（建议输入 100~200 个单词，越自然越好）。
* 打完后点击网页上的 **“完成并训练专属模型”**。
* 终端将自动完成训练，并生成 `user_profile.json`。

### 第二步：运行你的专属模拟器
训练完成后，在终端即可回放检验：
```bash
# 实时在终端以你自己的节奏回放
python3 personalized_simulator.py --realtime

# 输入指定文本进行回放
python3 personalized_simulator.py --text "Whatever text you want to simulate" --realtime

# 导出为 ESP32-S3 C++ 头文件
python3 personalized_simulator.py --text "My secret text" --export-c user_keystrokes.h
```
