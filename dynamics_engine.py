"""
人类击键动力学模型核心引擎 (Keystroke Dynamics Engine)
将输入文本转换为符合人类生物力学、肌肉记忆、生理延迟与认知节奏的按键事件流。
"""

import os
import sys
import random
import math
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from keyboard_layout import (
    KEY_COORDS, HAND_MAPPING, FINGER_MAPPING,
    ADJACENT_KEYS, SHIFT_SYMBOLS, FAST_DIGRAPHS, get_key_distance
)

class KeystrokeConfig:
    def __init__(
        self,
        target_wpm: float = 65.0,        # 目标基准打字速度 (Words Per Minute)
        dwell_mean: float = 85.0,        # 按键按下保持时间均值 (ms)
        dwell_std: float = 14.0,         # 按键按下保持时间标准差 (ms)
        typo_rate: float = 0.015,        # 手误打错率 (默认 1.5%)
        reaction_delay_min: float = 180, # 发现打错后的生理反应停顿 (ms)
        reaction_delay_max: float = 380,
        pause_sentence_min: float = 500, # 句末思考停顿 (ms)
        pause_sentence_max: float = 1300,
        pause_comma_min: float = 220,    # 逗号/分号停顿 (ms)
        pause_comma_max: float = 550,
        pause_newline_min: float = 700,  # 换行/段落思考停顿 (ms)
        pause_newline_max: float = 1800,
    ):
        self.target_wpm = target_wpm
        self.dwell_mean = dwell_mean
        self.dwell_std = dwell_std
        self.typo_rate = typo_rate
        self.reaction_delay_min = reaction_delay_min
        self.reaction_delay_max = reaction_delay_max
        self.pause_sentence_min = pause_sentence_min
        self.pause_sentence_max = pause_sentence_max
        self.pause_comma_min = pause_comma_min
        self.pause_comma_max = pause_comma_max
        self.pause_newline_min = pause_newline_min
        self.pause_newline_max = pause_newline_max


class KeyEvent:
    """单一按键事件对象"""
    def __init__(
        self,
        char: str,
        is_shift: bool,
        dwell_ms: float,
        flight_ms: float,
        is_typo: bool = False,
        is_backspace: bool = False
    ):
        self.char = char
        self.is_shift = is_shift
        self.dwell_ms = round(dwell_ms, 2)     # 按下持续时间
        self.flight_ms = round(flight_ms, 2)   # 距离上一个键释放的间隔时间
        self.is_typo = is_typo                 # 是否是误触键
        self.is_backspace = is_backspace       # 是否是退格修正

    def to_dict(self) -> Dict[str, Any]:
        return {
            "char": self.char,
            "shift": self.is_shift,
            "dwell": self.dwell_ms,
            "flight": self.flight_ms,
            "typo": self.is_typo,
            "bs": self.is_backspace
        }

    def __repr__(self) -> str:
        tag = "[BS]" if self.is_backspace else ("[TYPO]" if self.is_typo else "[OK]")
        return f"{tag} Char='{self.char}' Flight={self.flight_ms}ms Dwell={self.dwell_ms}ms"


class DynamicsEngine:
    def __init__(self, config: Optional[KeystrokeConfig] = None):
        self.cfg = config or KeystrokeConfig()
        # 基准周期 (ms / 字符): 1 WPM = 5 字符/分钟 = 300 字符/小时
        # 周期 = 60000 / (wpm * 5)
        self.base_cycle_ms = 60000.0 / (self.cfg.target_wpm * 5.0)

    def _sample_dwell_time(self, char: str) -> float:
        """采样按键按下时间 (Dwell Time)，符合截断高斯分布"""
        # 空格键通常偏长，小指按键略慢
        base_mean = self.cfg.dwell_mean
        if char == ' ':
            base_mean += 15.0
        elif char.lower() in ['q', 'z', 'p', '1', '0']:
            base_mean += 8.0

        val = random.gauss(base_mean, self.cfg.dwell_std)
        # 物理限制：一般人不可能低于 35ms（机械去抖），极少超过 220ms
        return max(38.0, min(val, 220.0))

    def _calculate_flight_time(self, prev_char: Optional[str], curr_char: str, speed_drift: float) -> float:
        """
        计算两键之间的飞行间隔 (Flight Time)
        融合双手交替、同指惩罚、物理键距、常见双字母组合(Digraphs)和自然认知延迟。
        """
        if prev_char is None:
            return random.uniform(80.0, 180.0)

        c1 = prev_char.lower()
        c2 = curr_char.lower()

        # 1. 基础飞行时间（由当前速度基准及动态漂移决定）
        # 飞行时间 = 字符基准周期 - 按键按下时间均值
        base_flight = max(30.0, (self.base_cycle_ms * speed_drift) - self.cfg.dwell_mean)
        flight = random.gauss(base_flight, base_flight * 0.22)

        # 2. 标点符号与认知停顿 (Cognitive Pause)
        if prev_char in ['.', '!', '?']:
            return random.uniform(self.cfg.pause_sentence_min, self.cfg.pause_sentence_max)
        elif prev_char in [',', ';', ':', '-']:
            return random.uniform(self.cfg.pause_comma_min, self.cfg.pause_comma_max)
        elif prev_char == '\n':
            return random.uniform(self.cfg.pause_newline_min, self.cfg.pause_newline_max)

        # 3. 常见词根双字母加速 (Fast Digraphs 肌肉记忆)
        bigram = c1 + c2
        if bigram in FAST_DIGRAPHS:
            flight *= random.uniform(0.60, 0.78)

        # 4. 键盘生理生物力学修正
        h1 = HAND_MAPPING.get(c1, 'R')
        h2 = HAND_MAPPING.get(c2, 'R')
        f1 = FINGER_MAPPING.get(c1, 3)
        f2 = FINGER_MAPPING.get(c2, 3)

        if h1 != h2:
            # 左右手交替：另一只手已提前就位，输入极快 (-20% ~ -35%)
            flight *= random.uniform(0.68, 0.82)
        else:
            # 同一只手
            if f1 == f2:
                # 同一个手指连续击打（如 'ed', 'ce' 或 双击 'oo', 'll'）
                # 需手指抬起并重新复位，速度明显放慢 (+30% ~ +60%)
                flight *= random.uniform(1.30, 1.65)
            else:
                # 同手不同指，取决于物理距离
                dist = get_key_distance(c1, c2)
                flight *= (0.90 + 0.08 * dist)

        # 5. 空格键后新词开头的微小迟疑 (+10% ~ +30%)
        if prev_char == ' ':
            flight *= random.uniform(1.10, 1.35)

        return max(22.0, flight)

    def _resolve_shift(self, char: str) -> (str, bool):
        """解析是否需要按下 Shift 键"""
        if char in SHIFT_SYMBOLS:
            return SHIFT_SYMBOLS[char], True
        if char.isupper():
            return char.lower(), True
        return char, False

    def generate_timeline(self, text: str) -> List[KeyEvent]:
        """
        核心方法：将输入字符串渲染为包含时序与退格纠错的事件流列表
        """
        events: List[KeyEvent] = []
        prev_char: Optional[str] = None

        # 模拟长时间打字的节奏波浪（随机游走漂移，模拟疲劳和专注状态）
        speed_drift = 1.0

        i = 0
        while i < len(text):
            target_char = text[i]

            # 每 10 个字符微调一次打字速度漂移因子 (0.85 ~ 1.18)
            if i % 8 == 0:
                speed_drift = max(0.82, min(1.20, speed_drift + random.uniform(-0.06, 0.06)))

            # 判断是否触发手误 (仅对字母且可替换的字符生效)
            c_lower = target_char.lower()
            trigger_typo = (
                self.cfg.typo_rate > 0
                and c_lower in ADJACENT_KEYS
                and random.random() < self.cfg.typo_rate
            )

            if trigger_typo:
                # 随机挑选一个物理相邻的键打错
                wrong_base = random.choice(ADJACENT_KEYS[c_lower])
                wrong_char = wrong_base.upper() if target_char.isupper() else wrong_base
                base_key, is_shift = self._resolve_shift(wrong_char)

                # 1. 敲下错误字符
                f_time = self._calculate_flight_time(prev_char, wrong_char, speed_drift)
                d_time = self._sample_dwell_time(wrong_char)
                events.append(KeyEvent(
                    char=wrong_char,
                    is_shift=is_shift,
                    dwell_ms=d_time,
                    flight_ms=f_time,
                    is_typo=True
                ))
                prev_char = wrong_char

                # 2. 反应迟疑：人类大脑需要反应时间发现打错了 (180 ~ 380ms)
                reaction_time = random.uniform(
                    self.cfg.reaction_delay_min,
                    self.cfg.reaction_delay_max
                )

                # 3. 按下退格键 Backspace
                bs_dwell = self._sample_dwell_time('\b')
                events.append(KeyEvent(
                    char='[Backspace]',
                    is_shift=False,
                    dwell_ms=bs_dwell,
                    flight_ms=reaction_time,
                    is_backspace=True
                ))
                prev_char = None  # 退格后手指重新定位

            # 正常敲下目标字符
            base_key, is_shift = self._resolve_shift(target_char)
            f_time = self._calculate_flight_time(prev_char, target_char, speed_drift)
            d_time = self._sample_dwell_time(target_char)

            events.append(KeyEvent(
                char=target_char,
                is_shift=is_shift,
                dwell_ms=d_time,
                flight_ms=f_time,
                is_typo=False
            ))

            prev_char = target_char
            i += 1

        return events
