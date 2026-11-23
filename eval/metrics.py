# -*- coding: utf-8 -*-
"""指标计算 + 混淆矩阵 + 表格渲染（纯标准库，不引入 pandas）。

指标定义（这几条定义本身就是要写进简历的东西）：

  动作准确率  pred_mode == gold_mode 的比例。
                ★ 产品指标。意图判错但动作判对（都转人工），业务上不算事故。
  意图准确率  pred_intent == gold_intent 的比例，只在 gold_intent 非空的样本上算。
                技术指标。用来定位"理解层"的能力，不直接决定业务风险。
  误拦率      该发的（gold 为 AUTO/CONFIRM）却被拦成 HUMAN/STOP。
                代价：人工白干 + 学员体验受损。
  漏放率      该人接的（gold 为 HUMAN/STOP）却被自动处理。
                代价：合规事故。这个指标的优先级高于一切。
  保守率      gold 为 AUTO 却降级成 CONFIRM。不算事故，但白吃人工成本。
"""


def width(s) -> int:
    """终端显示宽度：中文算 2 格。"""
    return sum(2 if ord(ch) > 127 else 1 for ch in str(s))


def pad(s, n: int, align: str = "left") -> str:
    s = str(s)
    gap = max(0, n - width(s))
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def table(headers, rows, aligns=None) -> str:
    aligns = aligns or ["left"] * len(headers)
    cols = [max([width(h)] + [width(r[i]) for r in rows]) for i, h in enumerate(headers)]
    line = "  ".join(pad(h, cols[i], aligns[i]) for i, h in enumerate(headers))
    sep = "  ".join("-" * cols[i] for i in range(len(headers)))
    body = [
        "  ".join(pad(r[i], cols[i], aligns[i]) for i in range(len(headers)))
        for r in rows
    ]
    return "\n".join([line, sep] + body)


def rate(num: int, den: int):
    return None if not den else num / den


def pct(num: int, den: int, digits: int = 1) -> str:
    r = rate(num, den)
    return "—" if r is None else f"{r * 100:.{digits}f}%"


def summarize(rows: list) -> dict:
    n = len(rows)

    action_total = sum(1 for r in rows if r.get("gold_mode"))
    action_ok = sum(1 for r in rows if r.get("gold_mode") and r["pred_mode"] == r["gold_mode"])

    intent_rows = [r for r in rows if r.get("gold_intent")]
    intent_ok = sum(1 for r in intent_rows if r["pred_intent"] == r["gold_intent"])

    send = [r for r in rows if r["gold_mode"] in ("AUTO", "CONFIRM")]
    human = [r for r in rows if r["gold_mode"] in ("HUMAN", "STOP")]
    auto = [r for r in rows if r["gold_mode"] == "AUTO"]

    false_block = [r for r in send if r["pred_mode"] not in ("AUTO", "CONFIRM")]
    false_allow = [r for r in human if r["pred_mode"] in ("AUTO", "CONFIRM")]
    conservative = [r for r in auto if r["pred_mode"] == "CONFIRM"]

    return {
        "n": n,
        "action": (action_ok, action_total),
        "intent": (intent_ok, len(intent_rows)),
        "false_block": (len(false_block), len(send)),
        "false_allow": (len(false_allow), len(human)),
        "conservative": (len(conservative), len(auto)),
        "false_block_rows": false_block,
        "false_allow_rows": false_allow,
        "conservative_rows": conservative,
    }


def confusion(rows: list, gold_key: str, pred_key: str, order=None):
    """返回 (labels, matrix, pairs)。matrix[gold][pred] = 次数。"""
    pairs = [(r[gold_key], r[pred_key]) for r in rows
             if r.get(gold_key) and r.get(pred_key)]
    labels = list(order) if order else sorted({x for pair in pairs for x in pair})
    matrix = {g: {p: 0 for p in labels} for g in labels}
    for g, p in pairs:
        if g in matrix and p in matrix[g]:
            matrix[g][p] += 1
    return labels, matrix, pairs


def off_diagonal(labels, matrix) -> list:
    """只取判错的格子，按次数降序。全对的模型不该被一张 11×11 的表格淹没。"""
    out = [(g, p, matrix[g][p]) for g in labels for p in labels
           if g != p and matrix[g][p]]
    out.sort(key=lambda x: (-x[2], x[0]))
    return out


def md_table(headers, rows) -> str:
    def cell(x):
        return str(x).replace("|", "\\|").replace("\n", " ")

    out = ["| " + " | ".join(cell(h) for h in headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(cell(x) for x in r) + " |" for r in rows]
    return "\n".join(out)
