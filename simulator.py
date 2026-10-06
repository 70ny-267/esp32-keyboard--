"""
击键动力学模拟器命令行工具 (Keystroke Simulator CLI)
功能：
1. 实时终端人机模拟回放（带退格与生理延迟效果）
2. 统计学分析报告（检验是否符合真实生物特征高斯分布）
3. 导出为 JSON 或 ESP32-S3 C++ 头文件
"""

import os
import sys
import time
import argparse
import json
from typing import List

# 确保无论从哪个工作目录运行，都能正确加载同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dynamics_engine import DynamicsEngine, KeystrokeConfig, KeyEvent

DEFAULT_DEMO_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "In computer security, keystroke dynamics refers to the detailed timing information "
    "which describes exactly when each key was pressed and when it was released. "
    "With proper statistical distribution, hardware emulators can mirror human nuances!"
)

def render_ascii_histogram(data: List[float], bins: int = 10, title: str = ""):
    """打印简易 ASCII 直方图，用于直观查看分布形态是否符合正态分布"""
    if not data:
        return
    min_v = min(data)
    max_v = max(data)
    if min_v == max_v:
        print(f"  {title}: 全部数据均为 {min_v:.1f}ms")
        return

    bin_width = (max_v - min_v) / bins
    counts = [0] * bins
    for v in data:
        idx = min(int((v - min_v) / bin_width), bins - 1)
        counts[idx] += 1

    max_count = max(counts) if counts else 1
    print(f"\n--- {title} 分布直方图 (统计检验) ---")
    for i in range(bins):
        low = min_v + i * bin_width
        high = low + bin_width
        bar = "█" * int(counts[i] / max_count * 32)
        print(f"  [{low:5.1f} - {high:5.1f} ms] | {bar:<32} ({counts[i]})")

def print_statistics(events: List[KeyEvent], total_chars_target: int):
    """打印击键动力学生物特征分析"""
    dwells = [e.dwell_ms for e in events]
    flights = [e.flight_ms for e in events]
    typo_count = sum(1 for e in events if e.is_typo)
    
    total_time_ms = sum(e.dwell_ms + e.flight_ms for e in events)
    total_seconds = total_time_ms / 1000.0
    
    # 标准打字测速公式：1 Word = 5 字符
    wpm = (total_chars_target / 5.0) / (total_seconds / 60.0) if total_seconds > 0 else 0
    
    mean_dwell = sum(dwells) / len(dwells) if dwells else 0
    std_dwell = (sum((x - mean_dwell)**2 for x in dwells) / len(dwells)) ** 0.5
    
    mean_flight = sum(flights) / len(flights) if flights else 0
    std_flight = (sum((x - mean_flight)**2 for x in flights) / len(flights)) ** 0.5

    print("\n" + "=" * 55)
    print("           人类击键动力学统计报告")
    print("=" * 55)
    print(f" 目标文本字符数   : {total_chars_target} 字符")
    print(f" 实际总按键事件   : {len(events)} 次 (含手误与退格)")
    print(f" 模拟手误发生次数 : {typo_count} 次 (手误率: {typo_count/total_chars_target*100:.2f}%)")
    print(f" 预计输入总耗时   : {total_seconds:.2f} 秒")
    print(f" 综合打字速度     : {wpm:.1f} WPM (Words Per Minute)")
    print("-" * 55)
    print(f" Dwell Time (按住) : 均值 = {mean_dwell:.1f} ms | 标准差 = {std_dwell:.1f} ms (范围: {min(dwells):.1f}~{max(dwells):.1f}ms)")
    print(f" Flight Time(间隔) : 均值 = {mean_flight:.1f} ms | 标准差 = {std_flight:.1f} ms (范围: {min(flights):.1f}~{max(flights):.1f}ms)")
    print("=" * 55)

    render_ascii_histogram(dwells, bins=8, title="按键按下时长 (Dwell Time)")
    render_ascii_histogram(flights, bins=8, title="键间转移时长 (Flight Time)")

def simulate_realtime(events: List[KeyEvent]):
    """在终端控制台实时逐字播放人类打字过程"""
    print("\n>>> 开始终端实时模拟打字 (按 Ctrl+C 中断)...")
    print("-" * 50)
    
    for ev in events:
        # 1. 等待飞行时间 (Key Up -> Next Key Down)
        time.sleep(ev.flight_ms / 1000.0)
        
        # 2. 模拟按键在终端上的表现
        if ev.is_backspace:
            # 退格退回一格并清空
            sys.stdout.write('\b \b')
            sys.stdout.flush()
        else:
            sys.stdout.write(ev.char)
            sys.stdout.flush()
            
        # 3. 按键按下时长 (Dwell)
        time.sleep(ev.dwell_ms / 1000.0)
        
    print("\n\n>>> 模拟打字完成！")

def export_to_c_header(events: List[KeyEvent], filepath: str):
    """导出为 ESP32-S3 Arduino C++ 兼容头文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("// Auto-generated Keystroke Dynamics Data for ESP32-S3\n")
        f.write("#pragma once\n#include <stdint.h>\n\n")
        f.write("struct KeyAction {\n")
        f.write("    char c;\n")
        f.write("    uint8_t shift;\n")
        f.write("    uint16_t flight_ms;\n")
        f.write("    uint16_t dwell_ms;\n")
        f.write("    uint8_t is_bs;\n")
        f.write("};\n\n")
        f.write(f"const int KEY_ACTIONS_COUNT = {len(events)};\n")
        f.write("const KeyAction PROGMEM KEY_ACTIONS[] = {\n")
        for ev in events:
            c_char = "'\\b'" if ev.is_backspace else (repr(ev.char) if ev.char != "'" else "'\\''")
            if ev.char == '\\':
                c_char = "'\\\\'"
            f.write(f"    {{{c_char}, {1 if ev.is_shift else 0}, {int(ev.flight_ms)}, {int(ev.dwell_ms)}, {1 if ev.is_backspace else 0}}},\n")
        f.write("};\n")
    print(f"\n[OK] 成功导出 ESP32 C++ 头文件: {filepath}")

def main():
    parser = argparse.ArgumentParser(description="人类击键动力学模型原型测试工具")
    parser.add_argument("--text", type=str, default="", help="要模拟输入的英文文本")
    parser.add_argument("--wpm", type=float, default=65.0, help="基准打字速度 (默认 65 WPM)")
    parser.add_argument("--typo", type=float, default=0.015, help="手误概率 (默认 0.015，即 1.5%%)")
    parser.add_argument("--realtime", action="store_true", help="开启终端真实时间回放显示")
    parser.add_argument("--export-json", type=str, default="", help="导出事件序列到 JSON 文件")
    parser.add_argument("--export-c", type=str, default="", help="导出事件序列到 ESP32 C++ 头文件")
    
    args = parser.parse_args()

    input_text = args.text if args.text else DEFAULT_DEMO_TEXT

    cfg = KeystrokeConfig(target_wpm=args.wpm, typo_rate=args.typo)
    engine = DynamicsEngine(cfg)
    
    print(f"正在对输入文本进行击键生物力学建模 ({len(input_text)} 字符)...")
    events = engine.generate_timeline(input_text)

    # 打印统计学检验报告
    print_statistics(events, len(input_text))

    # 导出文件
    if args.export_json:
        with open(args.export_json, 'w', encoding='utf-8') as f:
            json.dump([e.to_dict() for e in events], f, indent=2, ensure_ascii=False)
        print(f"[OK] 成功导出 JSON 数据: {args.export_json}")

    if args.export_c:
        export_to_c_header(events, args.export_c)

    # 实时回放
    if args.realtime:
        simulate_realtime(events)

if __name__ == "__main__":
    main()
