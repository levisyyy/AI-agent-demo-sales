# -*- coding: utf-8 -*-
"""第6层 风控闸门：所有对外输出必须过这一关。过不去就不发。"""
import re
from datetime import datetime
from . import db


def check(text: str, stage: str, now=None, is_reply: bool = False):
    """返回 (是否通过, 原因, 是否降级为草稿)

    静默时段的语义是「不许营销推送打扰人」，不是「不许回话」。
    学员主动发消息时，回复照常生成，但降级成人工确认的草稿再发。
    每次现读配置（DB），工作台里改禁语立即生效。
    """
    F = db.load_forbidden()

    if not text or not text.strip():
        return False, "空消息", False

    # 1. 硬禁语
    for w in F["hard_block"]:
        if w in text:
            return False, f"禁用词：{w}", False

    # 2. 价格数字——除D4/D5的既定话术外，一律不许出现金额
    #    先剔除链接，避免 URL 里的编号被误判成价格
    clean = re.sub(r"https?://\S+", "", text)
    for pat in F["price_patterns"]:
        m = re.search(pat, clean)
        if m and stage not in ("D4", "D5"):
            return False, f"出现金额/价格表述「{m.group()}」，该阶段不报价", False

    # 3. 静默时段：只拦主动推送，回复降级为草稿
    now = now or datetime.now()
    q = F["quiet_hours"]
    if now.hour >= q["start"] or now.hour < q["end"]:
        if is_reply:
            return True, "", True
        return False, f"静默时段（{q['start']}:00-{q['end']}:00）不发送营销内容", False

    # 4. 过长（不像人话）
    if len(text) > 200:
        return False, f"过长（{len(text)}字），像机器人", False

    return True, "", False
