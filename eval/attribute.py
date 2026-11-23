# -*- coding: utf-8 -*-
"""失败归因：把每一条错判钉到具体某一层。

这是整套评估里最值钱的部分。没有归因，报告只能告诉你"准确率 90%"，
不知道该改提示词、改策略矩阵、还是补话术卡片；有了归因，每条失败都变成一个待办。

归因原则：**取因果链上第一个偏离金标的层**。
意图判错时，后面策略、卡片、风控全都无意义，所以意图优先于它们。
"""

LAYERS = ["①闸门", "③意图识别", "④策略决策", "⑤话术卡片", "⑥风控闸门"]


def attribute(row: dict) -> str:
    """返回失败所在层；通过则返回空串。

    row 需要具备：pred_intent / gold_intent / gold_mode / pred_mode / blocked / guard
    """
    # 动作判对 → 不参与失败归因。
    # 注意：闸门"正拦"（该转人工也确实拦了）动作是对的，不能因为 pred_intent 为空
    # 就当成失败。意图偏差但动作对的情况，单独放在"值得复核"里看。
    if row.get("gold_mode") and row["pred_mode"] == row["gold_mode"]:
        return ""

    # 第1层：没有 intent 字段，说明在闸门就被挡了，压根没进模型
    if not row.get("pred_intent"):
        return "①闸门"

    # 第3层：意图判错（gold_intent 为 null 的样本不参与，比如高危词拦截）
    if row.get("gold_intent") and row["pred_intent"] != row["gold_intent"]:
        return "③意图识别"

    # 第5层：意图和动作都对，但这个场景没写卡片 —— "不许即兴发挥"兜底生效
    if row.get("blocked") == "无匹配话术卡片":
        return "⑤话术卡片"

    # 第6层：文本生成了，但没过禁语/报价/时段/长度
    if str(row.get("guard", "")).startswith("拦截"):
        return "⑥风控闸门"

    # 第4层：前面都正常，纯粹是矩阵给的档位不对，或硬规则/兜底把档位改了
    if row["pred_mode"] != row["gold_mode"]:
        return "④策略决策"

    return ""


def distribution(rows: list) -> dict:
    """{层名: 条数}，只统计失败样本。"""
    dist = {}
    for r in rows:
        layer = r.get("layer") or attribute(r)
        if layer:
            dist[layer] = dist.get(layer, 0) + 1
    return dist
