#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳中国 MCP 客户端（纯标准库，零第三方依赖）

协议: MCP Streamable HTTP (JSON-RPC 2.0)
端点: https://mcp.mcd.cn/mcp-servers/mcd-mcp
鉴权: Authorization: Bearer <TOKEN>

用法:
    from mcp_client import McpClient
    c = McpClient()                 # 自动读环境变量 MCD_MCP_TOKEN
    tools = c.list_tools()
    r = c.call("query-my-account", {})
"""

import json
import os
import sys
import uuid
import urllib.request
import urllib.error

DEFAULT_URL = "https://mcp.mcd.cn/mcp-servers/mcd-mcp"
FALLBACK_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, token=None, url=None, timeout=30, verbose=False):
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "")
        if not self.token:
            raise McpError(
                "未找到 MCP Token。请先 export MCD_MCP_TOKEN='你的token'\n"
                "申请地址: https://open.mcd.cn/mcp （手机号登录 → 控制台 → 激活）"
            )
        self.url = url or os.environ.get("MCD_MCP_URL", DEFAULT_URL)
        self.timeout = timeout
        self.verbose = verbose
        self.session_id = None
        self._initialized = False
        self._tried_fallback = False

    # ---------- 底层传输 ----------

    def _post(self, payload, include_session=True):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
        }
        if include_session and self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                new_sid = resp.headers.get("Mcp-Session-Id")
                if new_sid:
                    self.session_id = new_sid
                raw = resp.read().decode("utf-8", errors="replace")
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            if e.code == 401:
                raise McpError("401 Token 无效/已过期，请到 open.mcd.cn 重新激活")
            if e.code == 429:
                raise McpError("429 触发限流（600次/分钟），请降低调用频率")
            raise McpError("HTTP %s: %s" % (e.code, detail))
        except urllib.error.URLError as e:
            raise McpError("网络错误: %s" % e.reason)

        return self._parse(resp_status_ctype=ctype, raw=raw)

    def _parse(self, resp_status_ctype, raw):
        """响应可能是裸 JSON，也可能是 SSE 流。两种都解析。"""
        raw = raw.strip()
        if not raw:
            return None
        if "text/event-stream" in resp_status_ctype or raw.startswith("event:"):
            for line in raw.splitlines():
                if line.startswith("data:"):
                    chunk = line[5:].strip()
                    if chunk and chunk != "[DONE]":
                        try:
                            return json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise McpError("无法解析响应: %s" % raw[:300])

    def _rpc(self, method, params=None, notify=False):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = str(uuid.uuid4())
        return payload

    # ---------- 会话 ----------

    def initialize(self):
        resp = self._post(self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcd-points-guard", "version": "1.0.0"},
        }), include_session=False)

        if resp is None and not self._tried_fallback:
            # 端点可能有两个版本，回退一次
            self._tried_fallback = True
            self.url = FALLBACK_URL
            return self.initialize()

        if resp and "error" in resp:
            raise McpError("initialize 失败: %s" % resp["error"])
        # notifications/initialized 不需要回包
        try:
            self._post(self._rpc("notifications/initialized"), notify=True)
        except McpError:
            pass
        self._initialized = True
        return resp

    def _ensure(self):
        if not self._initialized:
            self.initialize()

    # ---------- 工具 ----------

    def list_tools(self):
        self._ensure()
        resp = self._post(self._rpc("tools/list"))
        if not resp or "error" in resp:
            raise McpError("tools/list 失败: %s" % (resp.get("error") if resp else "空响应"))
        return resp.get("result", {}).get("tools", [])

    def call(self, name, arguments=None):
        """调用工具，返回解析后的 Python 对象。"""
        self._ensure()
        resp = self._post(self._rpc("tools/call", {
            "name": name,
            "arguments": arguments or {},
        }))
        if not resp:
            raise McpError("%s 返回空响应" % name)
        if "error" in resp:
            raise McpError("%s 调用失败: %s" % (name, resp["error"]))

        result = resp.get("result", {})
        return self._unwrap(result)

    @staticmethod
    def _unwrap(result):
        """MCP content 通常是 [{'type':'text','text':'<json 或文本>'}]"""
        content = result.get("content")
        if not content:
            return result
        texts = []
        for c in content:
            if c.get("type") == "text":
                texts.append(c.get("text", ""))
            elif c.get("type") == "resource":
                texts.append(c.get("resource", {}).get("text", ""))
        blob = "\n".join(t for t in texts if t).strip()
        if not blob:
            return result
        # 尽量还原成 JSON
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            # 有些接口会在 JSON 前后加说明文字，尝试截取首个 {...} 或 [...]
            for opener, closer in (("{", "}"), ("[", "]")):
                i, j = blob.find(opener), blob.rfind(closer)
                if i != -1 and j > i:
                    try:
                        return json.loads(blob[i:j + 1])
                    except json.JSONDecodeError:
                        pass
            return blob

    # ---------- 便捷方法 ----------

    def safe_call(self, name, arguments=None):
        """永不抛异常的调用，用于探测阶段。"""
        try:
            return {"ok": True, "tool": name, "args": arguments or {}, "data": self.call(name, arguments)}
        except Exception as e:
            return {"ok": False, "tool": name, "args": arguments or {}, "error": str(e)}


def load_token_from_env_file(path=".env"):
    """可选：从 .env 读 token（.env 必须在 .gitignore 里）"""
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("MCD_MCP_TOKEN"):
                os.environ.setdefault("MCD_MCP_TOKEN", line.split("=", 1)[1].strip().strip("'\""))


if __name__ == "__main__":
    load_token_from_env_file()
    c = McpClient()
    tools = c.list_tools()
    print("共 %d 个工具可用:\n" % len(tools))
    for t in sorted(tools, key=lambda x: x.get("name", "")):
        print("  - %-28s %s" % (t.get("name"), (t.get("description") or "")[:60]))
