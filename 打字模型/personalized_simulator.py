"""
个性化击键动力学模拟器 (Personalized Keystroke Simulator)
加载经过个人数据训练的 user_profile.json，按完全属于你个人的肌肉记忆与击键生物特征生成输入流。
"""

import os
import sys
import time
import json
import random
import argparse
from typing import List, Dict, Any, Optional

# 导入通用布局库
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PARENT_DIR)
from keyboard_layout import (
    KEY_COORDS, HAND_MAPPING, FINGER_MAPPING,
    ADJACENT_KEYS, SHIFT_SYMBOLS, get_key_distance
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILE_PATH = os.path.join(BASE_DIR, "user_profile.json")

class PersonalizedEngine:
    def __init__(self, profile_data: Dict[str, Any]):
        self.p = profile_data
        self.g_dwell = self.p.get("global_dwell", {"mean": 85.0, "std": 15.0})
        self.g_flight = self.p.get("global_flight", {"mean": 115.0, "std": 35.0})
        self.dwell_by_key = self.p.get("dwell_by_key", {})
        self.bigrams = self.p.get("bigram_flights", {})
        self.space_pause = self.p.get("space_pause", {"mean": 130.0, "std": 30.0})
        self.punct_pause = self.p.get("punctuation_pause", {"mean": 450.0, "std": 120.0})
        self.typo_rate = self.p.get("typo_rate", 0.012)

    def sample_dwell(self, char: str) -> float:
        c = char.lower()
        if c in self.dwell_by_key:
            m = self.dwell_by_key[c]["mean"]
            s = self.dwell_by_key[c]["std"] or 10.0
            return max(35.0, random.gauss(m, s))
        return max(35.0, random.gauss(self.g_dwell["mean"], self.g_dwell["std"]))

    def sample_flight(self, prev_char: Optional[str], curr_char: str) -> float:
        if prev_char is None:
            return random.uniform(80.0, 160.0)

        c1 = prev_char.lower()
        c2 = curr_char.lower()

        # 1. 标点思考停顿
        if prev_char in [".", "!", "?", "\n"]:
            return max(250.0, random.gauss(self.punct_pause["mean"] * 1.5, self.punct_pause["std"]))
        elif prev_char in [",", ";", ":", "-"]:
            return max(150.0, random.gauss(self.punct_pause["mean"], self.punct_pause["std"]))

        # 2. 词间空格停顿
        if prev_char == " ":
            return max(50.0, random.gauss(self.space_pause["mean"], self.space_pause["std"]))

        # 3. 学习到的个人特定双键组合 (Bigram 肌肉记忆)
        bigram = c1 + c2
        if bigram in self.bigrams:
            bg_data = self.bigrams[bigram]
            return max(25.0, random.gauss(bg_data["mean"], max(8.0, bg_data["std"])))

        # 4. 未学到的普通字符：结合个人全局均值与物理键距生物力学
        base_f = random.gauss(self.g_flight["mean"], self.g_flight["std"])
        h1 = HAND_MAPPING.get(c1, 'R')
        h2 = HAND_MAPPING.get(c2, 'R')
        f1 = FINGER_MAPPING.get(c1, 3)
        f2 = FINGER_MAPPING.get(c2, 3)

        if h1 != h2:
            base_f *= 0.82  # 双手交替加速
        elif f1 == f2:
            base_f *= 1.40  # 同指连击惩罚
        else:
            dist = get_key_distance(c1, c2)
            base_f *= (0.92 + 0.07 * dist)

        return max(28.0, base_f)

    def _resolve_shift(self, char: str):
        if char in SHIFT_SYMBOLS:
            return SHIFT_SYMBOLS[char], True
        if char.isupper():
            return char.lower(), True
        return char, False

    def generate(self, text: str):
        events = []
        prev_char = None

        for target_char in text:
            c_lower = target_char.lower()
            # 个人手误率模拟
            if self.typo_rate > 0 and c_lower in ADJACENT_KEYS and random.random() < self.typo_rate:
                wrong_char = random.choice(ADJACENT_KEYS[c_lower])
                if target_char.isupper():
                    wrong_char = wrong_char.upper()
                _, is_shift = self._resolve_shift(wrong_char)

                # 误触键
                f_time = self.sample_flight(prev_char, wrong_char)
                d_time = self.sample_dwell(wrong_char)
                events.append({
                    "char": wrong_char, "shift": is_shift, "flight": round(f_time, 2),
                    "dwell": round(d_time, 2), "typo": True, "bs": False
                })
                # 生理反应延迟 + 退格
                react_delay = random.uniform(200.0, 360.0)
                bs_dwell = self.sample_dwell('\b')
                events.append({
                    "char": "[Backspace]", "shift": False, "flight": round(react_delay, 2),
                    "dwell": round(bs_dwell, 2), "typo": False, "bs": True
                })
                prev_char = None

            base_key, is_shift = self._resolve_shift(target_char)
            f_time = self.sample_flight(prev_char, target_char)
            d_time = self.sample_dwell(target_char)

            events.append({
                "char": target_char, "shift": is_shift, "flight": round(f_time, 2),
                "dwell": round(d_time, 2), "typo": False, "bs": False
            })
            prev_char = target_char

        return events


def simulate_realtime(events):
    print("\n>>> 开始按照【你个人的打字节奏】在终端实时回放...")
    print("-" * 55)
    for ev in events:
        time.sleep(ev["flight"] / 1000.0)
        if ev["bs"]:
            sys.stdout.write('\b \b')
            sys.stdout.flush()
        else:
            sys.stdout.write(ev["char"])
            sys.stdout.flush()
        time.sleep(ev["dwell"] / 1000.0)
    print("\n\n>>> 模拟打字完成！")

def export_c_header(events, filepath):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("// Personalized Keystroke Dynamics Data for ESP32-S3\n")
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
            c = "'\\b'" if ev["bs"] else (repr(ev["char"]) if ev["char"] != "'" else "'\\''")
            if ev["char"] == '\\':
                c = "'\\\\'"
            f.write(f"    {{{c}, {1 if ev['shift'] else 0}, {int(ev['flight'])}, {int(ev['dwell'])}, {1 if ev['bs'] else 0}}},\n")
        f.write("};\n")
    print(f"[OK] 成功导出个性化 ESP32 C++ 头文件: {filepath}")

def main():
    parser = argparse.ArgumentParser(description="个性化击键动力学模拟器")
    parser.add_argument("--profile", type=str, default=DEFAULT_PROFILE_PATH, help="个人打字模型文件路径")
    parser.add_argument("--text", type=str, default="", help="要模拟输入的文本")
    parser.add_argument("--realtime", action="store_true", help="开启终端真实时间回放")
    parser.add_argument("--export-c", type=str, default="", help="导出为 ESP32 C++ 头文件")
    parser.add_argument("--export-json", type=str, default="", help="导出为 JSON 文件")
    args = parser.parse_args()

    if not os.path.exists(args.profile):
        print(f"[提示] 未找到个人模型文件: {args.profile}")
        print("请先运行 `python3 collector.py` 采集你自己的打字数据并训练生成模型！")
        return

    with open(args.profile, "r", encoding="utf-8") as f:
        profile_data = json.load(f)

    sample_text = args.text if args.text else (
        "This paragraph is typed with your exact personal rhythm, "
        "reproducing your unique key press duration, flight intervals, and muscle memory."
    )

    engine = PersonalizedEngine(profile_data)
    events = engine.generate(sample_text)

    # 统计展示
    total_time = sum(e["dwell"] + e["flight"] for e in events) / 1000.0
    wpm = (len(sample_text) / 5.0) / (total_time / 60.0) if total_time > 0 else 0

    print("=" * 55)
    print("      加载专属模型生成打字事件")
    print("=" * 55)
    print(f" 模型来源       : {args.profile}")
    print(f" 训练集打字速度 : {profile_data.get('measured_wpm')} WPM")
    print(f" 当前生成耗时   : {total_time:.2f} 秒 (综合速度: {wpm:.1f} WPM)")
    print(f" 生成按键动作   : {len(events)} 次")
    print("=" * 55)

    if args.export_json:
        with open(args.export_json, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print(f"[OK] 导出 JSON: {args.export_json}")

    if args.export_c:
        export_c_header(events, args.export_c)

    if args.realtime:
        simulate_realtime(events)

if __name__ == "__main__":
    main()
