"""端到端测试：假 OpenAI 兼容服务器 + 后端全链路验证。

启动一个假的 OpenAI 兼容 API（127.0.0.1:9898），提供 /models 和 /chat/completions，
配合 EMOERA_ALLOW_PRIVATE=1 让后端允许访问它，验证：
1. 自动获取模型列表
2. 测试连接
3. AI 速报生成（含 AI 总结）
"""
import json
import threading
import urllib.request
import urllib.error
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

MODELS = ["deepseek-chat", "deepseek-reasoner", "gpt-4o-mini", "qwen-plus"]
LOG = []


class FakeOpenAI(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        LOG.append(("GET", self.path, dict(self.headers)))
        if self.path.rstrip("/").endswith("/models"):
            self._json({"object": "list", "data": [{"id": m, "object": "model"} for m in MODELS]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "ignore")
        LOG.append(("POST", self.path, body[:120]))
        self._json({"choices": [{"message": {"role": "assistant", "content": "连接成功"}}]})

    def log_message(self, *a):
        pass


def main():
    srv = HTTPServer(("127.0.0.1", 9898), FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.5)
    print("=== 假 OpenAI 服务器已启动 (127.0.0.1:9898) ===")

    def req(path, data=None):
        method = "POST" if data is not None else "GET"
        body = json.dumps(data).encode() if data is not None else None
        r = urllib.request.Request(
            f"http://127.0.0.1:8000{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            resp = urllib.request.urlopen(r)
            return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode())
            except Exception:
                return e.code, {}

    # 1. 配置 base_url 指向假服务器
    st, d = req("/api/v1/settings/ai", {"base_url": "http://127.0.0.1:9898/v1", "model": ""})
    print("1) 保存 base_url:", st, d.get("base_url"))

    # 2. 自动获取模型
    st, d = req("/api/v1/settings/ai/models", {"api_key": "sk-fake"})
    print("2) 自动获取模型:", st, "models:", d.get("models"))

    # 3. 测试连接
    st, d = req("/api/v1/settings/ai/test", {"api_key": "sk-fake"})
    print("3) 测试连接:", st, d.get("message"), "| model:", d.get("model"))

    # 4. 触发 AI 速报（应带 AI 总结）—— 用 POST
    st, d = req("/api/v1/news/brief/refresh", {"refresh": True})
    print("4) AI 速报:", st, "| using_ai:", d.get("using_ai"))
    if d.get("using_ai"):
        print("   overview:", d.get("overview"))
        for sec in d.get("sections", []):
            print(f"   [{sec['key']}] summary: {sec.get('summary')[:50]}")

    print("=== 假服务器收到的请求 ===")
    for kind, path, extra in LOG:
        print(f"  {kind} {path}")

    srv.shutdown()


if __name__ == "__main__":
    main()
