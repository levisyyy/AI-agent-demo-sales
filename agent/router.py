# -*- coding: utf-8 -*-
"""第3层 意图识别：小模型 / temp=0 / 强制 JSON。要求是稳定，不是聪明。"""
import json
import re
from .models import Intent, LLM

INTENTS = ["到课提醒", "临时改约", "师资咨询", "课程咨询", "价格咨询",
           "异议嫌贵", "犹豫", "情绪安抚", "转化铺垫", "尾款提醒", "无效内容"]

# ---- mock 模式：关键词规则，无 key 也能演示全流程 ----
# 顺序即优先级：涉及钱的意图（价格咨询）必须排在转化/尾款之前，
# 保证"进阶班多少钱"仍然判成价格咨询（人接），不会被"进阶班"抢成转化铺垫。
RULES = [
    ("临时改约", ["去不了", "改天", "改到", "加班", "有事", "来不及", "请假", "明天再"]),
    ("异议嫌贵", ["贵", "便宜", "折扣", "优惠", "太贵", "划算", "值不值"]),
    ("犹豫", ["考虑", "想想", "再说", "对比", "商量", "看看"]),
    ("价格咨询", ["多少钱", "价格", "费用", "学费", "怎么付"]),
    ("尾款提醒", ["尾款", "补齐", "交齐", "补款", "还差多少"]),
    ("转化铺垫", ["进阶班", "报名", "名额", "占位", "订金", "定金", "怎么加入"]),
    ("师资咨询", ["老师", "师资", "哪个学校", "哪毕业", "什么背景", "教了多久"]),
    ("课程咨询", ["几点", "讲什么", "回放", "课程", "内容", "多久", "链接"]),
    ("情绪安抚", ["累", "难", "放弃", "学不会", "烦", "没意思", "压力"]),
]
NEG_WORDS = ["贵", "烦", "累", "退", "不想", "没用", "失望", "算了"]


def _mock_classify(text: str) -> Intent:
    for name, kws in RULES:
        hit = [k for k in kws if k in text]
        if hit:
            conf = 0.9 if len(hit) >= 2 else 0.82
            emo = "负面" if any(w in text for w in NEG_WORDS) else "中性"
            return Intent(name, conf, emo)
    return Intent("无效内容", 0.5, "中性")


SYS = """你是教育机构私域运营的意图分类器。只做分类，不回答问题。
可选意图：%s
输出严格 JSON：{"intent": "...", "confidence": 0到1的小数, "emotion": "中性"或"负面"}
confidence 表示你对判断的把握，不要一律给高分。""" % "、".join(INTENTS)


def classify(text: str, llm: LLM) -> Intent:
    if llm.available:
        raw = llm.chat(SYS, f"学员说：{text}", temperature=0, json_mode=True)
        if raw:
            try:
                d = json.loads(raw)
                name = d.get("intent", "无效内容")
                if name not in INTENTS:
                    name = "无效内容"
                return Intent(name, float(d.get("confidence", 0.6)), d.get("emotion", "中性"))
            except Exception:
                pass
    return _mock_classify(text)


def classify_event(trigger: str) -> Intent:
    """定时事件不走模型：提醒就是提醒，确定性 1.0"""
    return Intent("到课提醒", 1.0, "中性")
