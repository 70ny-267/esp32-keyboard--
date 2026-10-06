"""
个人打字生物特征指纹训练器 (Personal Keystroke Profile Trainer)
从高精度击键事件序列中提取并拟合个人的生物力学特征、习惯延迟与双键转移矩阵。
"""

import json
import math
from typing import List, Dict, Any

def mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0

def std(vals: List[float], avg: float) -> float:
    if len(vals) < 2:
        return 0.0
    variance = sum((x - avg) ** 2 for x in vals) / len(vals)
    return math.sqrt(variance)

def percentile(vals: List[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)

class ProfileTrainer:
    def __init__(self, raw_events: List[Dict[str, Any]]):
        self.raw_events = raw_events

    def train(self) -> Dict[str, Any]:
        if not self.raw_events:
            raise ValueError("无击键数据可供训练")

        dwells = [e["dwell"] for e in self.raw_events if e.get("dwell", 0) > 0]
        # 排除首键的 0 飞行时间和异常卡顿 (如离开电脑超过 4 秒的停顿)
        flights = [e["flight"] for e in self.raw_events[1:] if 0 < e.get("flight", 0) < 4000]

        # 1. 全局 Dwell Time 指标
        d_mean = mean(dwells)
        d_std = std(dwells, d_mean)

        # 2. 全局 Flight Time 指标
        f_mean = mean(flights)
        f_std = std(flights, f_mean)

        # 3. 按键特定 Dwell 映射 (每个键专属的按压保持习惯)
        dwell_by_key = {}
        key_dwell_map: Dict[str, List[float]] = {}
        for e in self.raw_events:
            k = e["key"].lower()
            key_dwell_map.setdefault(k, []).append(e["dwell"])

        for k, v in key_dwell_map.items():
            if len(v) >= 2:
                m = mean(v)
                dwell_by_key[k] = {
                    "mean": round(m, 2),
                    "std": round(std(v, m), 2),
                    "count": len(v)
                }

        # 4. 双键组合转移时间矩阵 (Bigram Transition Matrix)
        bigram_flights: Dict[str, Dict[str, Any]] = {}
        bigram_map: Dict[str, List[float]] = {}
        for i in range(len(self.raw_events) - 1):
            k1 = self.raw_events[i]["key"].lower()
            k2 = self.raw_events[i+1]["key"].lower()
            fl = self.raw_events[i+1].get("flight", 0)
            if 0 < fl < 2500 and len(k1) == 1 and len(k2) == 1:
                bg = k1 + k2
                bigram_map.setdefault(bg, []).append(fl)

        for bg, fl_list in bigram_map.items():
            if len(fl_list) >= 2:
                m = mean(fl_list)
                bigram_flights[bg] = {
                    "mean": round(m, 2),
                    "std": round(std(fl_list, m), 2),
                    "count": len(fl_list)
                }

        # 5. 空格键与词间转移停顿
        space_flights = [e["flight"] for e in self.raw_events if e["key"] == " " and 0 < e.get("flight", 0) < 3000]
        space_mean = mean(space_flights) if space_flights else f_mean
        space_std = std(space_flights, space_mean) if space_flights else f_std

        # 6. 标点符号思考停顿
        punct_flights = []
        for i in range(len(self.raw_events) - 1):
            if self.raw_events[i]["key"] in [".", ",", "!", "?", ";", ":"]:
                fl = self.raw_events[i+1].get("flight", 0)
                if 0 < fl < 4000:
                    punct_flights.append(fl)
        
        punct_mean = mean(punct_flights) if punct_flights else f_mean * 2.0
        punct_std = std(punct_flights, punct_mean) if punct_flights else f_std

        # 7. 手误与退格特征
        bs_count = sum(1 for e in self.raw_events if e["key"] == "Backspace")
        typo_rate = round(bs_count / len(self.raw_events), 4)

        # 8. 测量 WPM
        total_time_ms = self.raw_events[-1]["timestamp"] - self.raw_events[0]["timestamp"]
        total_min = total_time_ms / 60000.0 if total_time_ms > 0 else 1.0
        measured_wpm = round((len(self.raw_events) / 5.0) / total_min, 1)

        profile = {
            "version": "1.0",
            "sample_keystrokes_count": len(self.raw_events),
            "measured_wpm": measured_wpm,
            "typo_rate": typo_rate,
            "global_dwell": {
                "mean": round(d_mean, 2),
                "std": round(d_std, 2),
                "min": round(min(dwells), 2) if dwells else 0,
                "max": round(max(dwells), 2) if dwells else 0,
                "p25": round(percentile(dwells, 0.25), 2),
                "p50": round(percentile(dwells, 0.50), 2),
                "p75": round(percentile(dwells, 0.75), 2),
            },
            "global_flight": {
                "mean": round(f_mean, 2),
                "std": round(f_std, 2),
                "min": round(min(flights), 2) if flights else 0,
                "max": round(max(flights), 2) if flights else 0,
                "p50": round(percentile(flights, 0.50), 2),
            },
            "space_pause": {
                "mean": round(space_mean, 2),
                "std": round(space_std, 2)
            },
            "punctuation_pause": {
                "mean": round(punct_mean, 2),
                "std": round(punct_std, 2)
            },
            "dwell_by_key": dwell_by_key,
            "bigram_flights": bigram_flights
        }

        return profile
