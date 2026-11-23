# -*- coding: utf-8 -*-
"""离线回放评估入口。

用法：
  python eval/run_eval.py                   # 跑默认金标集
  python eval/run_eval.py --cases a.jsonl   # 指定评估集
  python eval/run_eval.py --verbose         # 逐条打印判定过程
  python eval/run_eval.py --out ./reports   # 指定报告目录

设计要点：
- 每条样本前 store.reset()，保证样本之间互不污染（否则前一条推进了 Stage，
  后一条就走另一行策略，指标全是假的）。
- 留痕写到 eval/reports/eval_trace.jsonl，不脏主目录的 trace.jsonl。
- 时间固定 19:30，否则 22:00-8:00 静默时段会把所有主动推送拦掉。
"""
import argparse
import csv
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REPORT_DIR = os.path.join(ROOT, "eval", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)
os.environ.setdefault("TRACE_PATH", os.path.join(REPORT_DIR, "eval_trace.jsonl"))

from agent import Event, LLM, run, store                                    # noqa: E402
from eval.attribute import LAYERS, attribute, distribution                  # noqa: E402
from eval.dataset import load_cases                                        # noqa: E402
from eval.metrics import (confusion, md_table, off_diagonal, pct,          # noqa: E402
                          summarize, table, width)

NOW = datetime(2026, 11, 23, 19, 30)
MODE_ORDER = ["AUTO", "CONFIRM", "HUMAN", "STOP"]


def clip(s, n):
    s = str(s)
    if width(s) <= n:
        return s
    out, w = "", 0
    for ch in s:
        cw = 2 if ord(ch) > 127 else 1
        if w + cw > n - 1:
            break
        out += ch
        w += cw
    return out + "…"


def replay(cases, llm):
    with open(os.environ["TRACE_PATH"], "w", encoding="utf-8"):
        pass  # 清空上一次的评估留痕

    rows = []
    for c in cases:
        store.reset()                                   # ← 每条样本独立起点
        ev = Event(c["kind"], c["student_id"], c.get("text", ""), c.get("trigger", ""))
        r = run(ev, llm, now=NOW)

        row = {
            "id": c["id"],
            "student_id": c["student_id"],
            "student": r.trace.get("student", ""),
            "stage": r.trace.get("stage", ""),
            "kind": c["kind"],
            "text": c.get("text", "") or f"（定时：{c.get('trigger', '')}）",
            "gold_intent": c.get("gold_intent") or "",
            "gold_mode": c["gold_mode"],
            "pred_intent": r.intent.name if r.intent else "",
            "pred_mode": r.mode,
            "confidence": f"{r.intent.confidence:.2f}" if r.intent else "",
            "card": r.plan.card_id if r.plan else "",
            "blocked": r.blocked,
            "reason": r.plan.reason if r.plan else "",
            "guard": str(r.trace.get("guard", "")),
            "draft": r.draft,
            "note": c.get("note", ""),
        }
        row["action_ok"] = row["pred_mode"] == row["gold_mode"]
        row["intent_ok"] = (not row["gold_intent"]) or row["pred_intent"] == row["gold_intent"]
        row["layer"] = attribute(row)
        rows.append(row)
    return rows


def why(row):
    """失败原因：优先用拦截原因，其次用决策依据。"""
    return row["blocked"] or row["reason"] or row["guard"] or "—"


def build_markdown(rows, llm, cases_path):
    s = summarize(rows)
    dist = distribution(rows)
    fails = [r for r in rows if not r["action_ok"]]
    model = f"真实模型 {llm.model}" if llm.available else "MOCK（未配置 LLM_API_KEY）"

    parts = [
        "# AI 督学 Agent · 离线评估报告",
        "",
        f"- 评估集：`{os.path.relpath(cases_path, ROOT)}`（{s['n']} 条）",
        f"- 模型：{model}",
        f"- 回放时刻：{NOW:%Y-%m-%d %H:%M}",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
    ]
    if not llm.available:
        parts += ["> ⚠️ MOCK 模式下意图靠关键词规则、话术靠模板填充，",
                  "> 以下数字反映的是**规则与流程逻辑**，不代表真实模型能力。",
                  "> 配置 `LLM_API_KEY` 后必须在同一评估集上重跑，两份数字要分开讲。", ""]

    parts += ["## 一、核心指标", "",
              md_table(["指标", "数值", "比率", "含义"], [
                  ["动作准确率", f"{s['action'][0]}/{s['action'][1]}", pct(*s["action"]),
                   "产品指标：动作对了，业务上就不算事故"],
                  ["意图准确率", f"{s['intent'][0]}/{s['intent'][1]}", pct(*s["intent"]),
                   "技术指标：只在未被闸门拦截的样本上算"],
                  ["误拦率", f"{s['false_block'][0]}/{s['false_block'][1]}", pct(*s["false_block"]),
                   "该发的被拦成转人工，白吃人工成本"],
                  ["漏放率", f"{s['false_allow'][0]}/{s['false_allow'][1]}", pct(*s["false_allow"]),
                   "该人接的被自动处理 —— 事故级，优先级最高"],
                  ["保守率", f"{s['conservative'][0]}/{s['conservative'][1]}", pct(*s["conservative"]),
                   "该 AUTO 的降成 CONFIRM，不算事故但浪费人力"],
              ]), ""]

    parts += ["## 二、失败归因（按根因层）", ""]
    if dist:
        total_fail = sum(dist.values())
        parts.append(md_table(
            ["层", "条数", "占比"],
            [[k, v, pct(v, total_fail)] for k, v in
             sorted(dist.items(), key=lambda x: LAYERS.index(x[0]) if x[0] in LAYERS else 99)]
        ))
    else:
        parts.append("无失败样本。")

    labels, matrix, _ = confusion(rows, "gold_intent", "pred_intent")
    parts += ["", "## 三、意图混淆矩阵（仅判错的格子）", ""]
    off = off_diagonal(labels, matrix)
    if off:
        parts.append(md_table(["期望意图", "被判成", "次数"],
                              [[g, p, c] for g, p, c in off]))
    else:
        parts.append("意图全部判对。")

    parts += ["", "## 四、动作混淆矩阵", ""]
    mlabels, mmatrix, _ = confusion(rows, "gold_mode", "pred_mode", order=MODE_ORDER)
    head = ["期望 \\ 实际"] + mlabels
    body = [[g] + [mmatrix[g][p] for p in mlabels] for g in mlabels]
    parts.append(md_table(head, body))

    parts += ["", f"## 五、失败明细（{len(fails)} 条）", ""]
    if fails:
        parts.append(md_table(
            ["ID", "学员", "Stage", "输入", "期望", "实际", "归因", "原因"],
            [[r["id"], r["student"], r["stage"], r["text"],
              r["gold_mode"], r["pred_mode"], r["layer"] or "（通过）", why(r)]
             for r in fails]
        ))
    else:
        parts.append("无。")

    parts += ["", "## 六、通过但值得复核的样本", "",
              "以下样本动作判对了，但意图与人工判断不同。动作对不等于理解对，",
              "这类样本通常在提示词或规则上还有优化空间。", ""]
    soft = [r for r in rows if r["action_ok"] and not r["intent_ok"]]
    if soft:
        parts.append(md_table(["ID", "输入", "期望意图", "实际意图", "备注"],
                              [[r["id"], r["text"], r["gold_intent"], r["pred_intent"], r["note"]]
                               for r in soft]))
    else:
        parts.append("无。")

    return "\n".join(parts) + "\n"


def print_console(rows, llm, verbose=False):
    s = summarize(rows)
    dist = distribution(rows)

    print("=" * 70)
    print(" AI 督学 Agent · 离线评估")
    print(f" 样本 {s['n']} 条 ｜ 模型 {'真实模型 ' + llm.model if llm.available else 'MOCK'}"
          f" ｜ 回放时刻 {NOW:%Y-%m-%d %H:%M}")
    print("=" * 70)
    if not llm.available:
        print("\n⚠ MOCK 模式：数字只反映规则与模板逻辑，不代表真实模型能力。\n")

    print("一、核心指标")
    print(table(
        ["指标", "数值", "比率", "含义"],
        [["动作准确率", f"{s['action'][0]}/{s['action'][1]}", pct(*s["action"]), "产品指标"],
         ["意图准确率", f"{s['intent'][0]}/{s['intent'][1]}", pct(*s["intent"]), "技术指标"],
         ["误拦率", f"{s['false_block'][0]}/{s['false_block'][1]}", pct(*s["false_block"]), "该发被拦"],
         ["漏放率", f"{s['false_allow'][0]}/{s['false_allow'][1]}", pct(*s["false_allow"]), "★事故级"],
         ["保守率", f"{s['conservative'][0]}/{s['conservative'][1]}", pct(*s["conservative"]), "白吃人力"]],
        ["left", "right", "right", "left"]
    ))

    print("\n二、失败归因")
    if dist:
        print(table(["层", "条数"],
                    [[k, v] for k, v in
                     sorted(dist.items(), key=lambda x: LAYERS.index(x[0]) if x[0] in LAYERS else 99)],
                    ["left", "right"]))
    else:
        print("  无失败样本")

    fails = [r for r in rows if not r["action_ok"]]
    print(f"\n三、动作判错的样本（{len(fails)} 条）")
    if fails:
        print(table(
            ["ID", "学员", "期望", "实际", "归因", "原因"],
            [[r["id"], r["student"], r["gold_mode"], r["pred_mode"],
              r["layer"], clip(why(r), 34)] for r in fails]
        ))
    else:
        print("  无")

    soft = [r for r in rows if r["action_ok"] and not r["intent_ok"]]
    if soft:
        print(f"\n四、动作对但意图判错的样本（{len(soft)} 条）—— 理解层还有空间")
        print(table(["ID", "输入", "期望意图", "实际意图"],
                    [[r["id"], clip(r["text"], 22), r["gold_intent"], r["pred_intent"]]
                     for r in soft]))

    if verbose:
        print("\n五、逐条明细")
        for r in rows:
            flag = "✓" if r["action_ok"] else "✗"
            print(f"  {flag} {r['id']} {r['student']}({r['stage']}) "
                  f"{clip(r['text'], 20):<22} 期望 {r['gold_mode']:<8} 实际 {r['pred_mode']:<8}"
                  f"{r['layer']}")


def main():
    ap = argparse.ArgumentParser(description="离线回放评估")
    ap.add_argument("--cases", default=os.path.join(ROOT, "eval", "cases", "gold.jsonl"))
    ap.add_argument("--out", default=REPORT_DIR)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    cases = load_cases(args.cases)
    llm = LLM()
    rows = replay(cases, llm)

    print_console(rows, llm, args.verbose)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(args.out, f"report_{stamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_markdown(rows, llm, args.cases))

    csv_path = os.path.join(args.out, f"results_{stamp}.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n报告：{os.path.relpath(md_path, ROOT)}")
    print(f"明细：{os.path.relpath(csv_path, ROOT)}")


if __name__ == "__main__":
    main()
