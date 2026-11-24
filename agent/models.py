# -*- coding: utf-8 -*-
"""数据结构 + 模型客户端（零第三方依赖，mock 模式可直接跑）"""
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _load_dotenv():
    """读项目根的 .env（每行 key=value），只补空缺，不覆盖已有环境变量。

    .env 被 .gitignore 排除，密钥只留在本机；保持零依赖，不引 python-dotenv。
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v


_load_dotenv()


def load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------- 数据结构 ----------------
@dataclass
class Student:
    id: str
    name: str
    phone: str
    channel: str
    course: str
    stage: str
    enrolled_days: int
    attended: list
    touch_count: int
    last_reply_hours: Optional[float]
    tags: list = field(default_factory=list)
    concerns: list = field(default_factory=list)
    paid_deposit: bool = False
    paid_final: bool = False      # 尾款是否结清——只有它能让 D5 归档，订金不算


@dataclass
class Event:
    """输入事件：message=学员发来消息 / timer=定时触发"""
    kind: str                 # "message" | "timer"
    student_id: str
    text: str = ""
    trigger: str = ""         # timer 专用，如 "class_reminder"


@dataclass
class Intent:
    name: str
    confidence: float
    emotion: str = "中性"


@dataclass
class Plan:
    mode: str                 # AUTO | CONFIRM | HUMAN | STOP  —— 这就是人机边界
    card_id: str = ""
    freedom: str = ""
    reason: str = ""
    tools: list = field(default_factory=list)      # 真正要调用的工具
    guards: list = field(default_factory=list)     # 约束说明（如"不报价"）


@dataclass
class Result:
    ok: bool
    mode: str
    draft: str = ""
    intent: Optional[Intent] = None
    plan: Optional[Plan] = None
    blocked: str = ""
    trace: dict = field(default_factory=dict)


# ---------------- 模型客户端 ----------------
class LLM:
    """有 key 走真模型（OpenAI 兼容），没有就走 mock，保证 demo 今晚就能跑。"""

    def __init__(self):
        self.key = os.getenv("LLM_API_KEY", "").strip()
        self.base = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")
        self.last_error = ""
        self.calls = []   # 每次真实模型调用的明细（prompt/回复/耗时），供留痕与分析

    @property
    def available(self):
        return bool(self.key)

    @staticmethod
    def _clip(s, n: int = 400):
        s = str(s or "")
        return s if len(s) <= n else s[:n] + "…(截断)"

    def _record(self, system, user, response, started, ok):
        self.calls.append({
            "system": self._clip(system), "user": self._clip(user),
            "response": self._clip(response),
            "elapsed_ms": int((time.time() - started) * 1000), "ok": ok,
        })

    def chat(self, system: str, user: str, temperature: float = 0.3,
             json_mode: bool = False) -> Optional[str]:
        """json_mode 只给意图分类用；话术生成必须走纯文本，否则会把 JSON 原文发给学员。"""
        if not self.available:
            return None
        self.last_error = ""
        started = time.time()
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{self.base}/chat/completions", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            self._record(system, user, content, started, True)
            return content
        except Exception as e:
            # 静默降级到模板，但把原因留下来，否则接真模型时无从排查
            self.last_error = f"{type(e).__name__}: {e}"
            self._record(system, user, self.last_error, started, False)
            return None


__all__ = ["Student", "Event", "Intent", "Plan", "Result", "LLM", "load", "asdict"]
