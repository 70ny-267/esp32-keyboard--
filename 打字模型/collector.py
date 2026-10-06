"""
个人打字采集服务 (Keystroke Collector Server)
运行本脚本将启动本地 Web 服务，并在浏览器中打开数据采集页面。
输入完成后自动训练并输出专属打字生物特征模型 (user_profile.json)。
"""

import os
import sys
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from trainer import ProfileTrainer

PORT = 8765
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "collector.html")
RAW_DATA_PATH = os.path.join(BASE_DIR, "raw_keystrokes.json")
PROFILE_PATH = os.path.join(BASE_DIR, "user_profile.json")

class CollectorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            if os.path.exists(HTML_PATH):
                with open(HTML_PATH, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "collector.html Not Found")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/save_sample":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body.decode("utf-8"))
                events = data.get("events", [])

                if not events:
                    raise ValueError("未收到有效击键事件")

                # 1. 保存原始采集数据
                with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(events, f, indent=2, ensure_ascii=False)

                # 2. 训练专属生物力学模型
                trainer = ProfileTrainer(events)
                profile = trainer.train()

                # 3. 输出模型文件
                with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                    json.dump(profile, f, indent=2, ensure_ascii=False)

                # 响应前端
                resp = json.dumps({"success": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

                # 在控制台打印个人特征统计
                self.print_summary(profile)

            except Exception as e:
                err_resp = json.dumps({"success": False, "error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_resp)))
                self.end_headers()
                self.wfile.write(err_resp)
        else:
            self.send_error(404)

    def print_summary(self, p):
        print("\n" + "=" * 58)
        print("          🎉 专属个人打字生物特征模型训练完成！")
        print("=" * 58)
        print(f" 采集有效击键样本 : {p['sample_keystrokes_count']} 次")
        print(f" 你的真实打字速度 : {p['measured_wpm']} WPM")
        print(f" 你的真实手误概率 : {p['typo_rate']*100:.2f}%")
        print("-" * 58)
        print(f" 专属 Dwell Time (按键保持) : 均值 {p['global_dwell']['mean']} ms | 中位数 {p['global_dwell']['p50']} ms (标准差: {p['global_dwell']['std']}ms)")
        print(f" 专属 Flight Time (键间间隔): 均值 {p['global_flight']['mean']} ms | 中位数 {p['global_flight']['p50']} ms (标准差: {p['global_flight']['std']}ms)")
        print(f" 词间空格停顿均值           : {p['space_pause']['mean']} ms")
        print(f" 标点符号思考停顿均值       : {p['punctuation_pause']['mean']} ms")
        print(f" 已学习的肌肉记忆双键组合   : {len(p['bigram_flights'])} 组 (如: {list(p['bigram_flights'].keys())[:8]}...)")
        print("-" * 58)
        print(f" [OK] 模型已保存在: {PROFILE_PATH}")
        print(" 现在可以使用个性化模拟器或将数据编译至硬件固件中！")
        print("=" * 58 + "\n")

    def log_message(self, format, *args):
        # 简化 HTTP 日志输出
        return

def run_server():
    port = PORT
    server_address = ("127.0.0.1", port)
    try:
        httpd = HTTPServer(server_address, CollectorHandler)
    except OSError:
        # 端口占用时自动切换端口
        port = 8766
        server_address = ("127.0.0.1", port)
        httpd = HTTPServer(server_address, CollectorHandler)

    url = f"http://127.0.0.1:{port}"
    print(f"\n=======================================================")
    print(f"   打字数据采集服务已就绪！")
    print(f"   请在浏览器中打开: {url}")
    print(f"   正在自动为你打开浏览器...")
    print(f"   (输入完成并点击网页提交后，终端会自动生成模型)")
    print(f"=======================================================\n")
    
    webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n采集服务已安全退出。")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
