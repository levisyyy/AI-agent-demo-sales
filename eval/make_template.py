# -*- coding: utf-8 -*-
"""把原始消息批量转成待标注骨架，省掉手写 JSON 的功夫。

输入 raw_messages.txt，每行 `学员ID|学员原话`（空行和 # 开头的行忽略）
输出 to_label.jsonl，gold_intent / gold_mode 留空待填，_stage 是提示不是答案。

填完把文件改名成 gold.jsonl 就能直接跑 run_eval.py。

用法：
  python eval/make_template.py
  python eval/make_template.py --src my_raw.txt --out eval/cases/to_label.jsonl
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CASES_DIR = os.path.join(ROOT, "eval", "cases")


def read_students():
    with open(os.path.join(ROOT, "data", "students.json"), encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="生成待标注骨架")
    ap.add_argument("--src", default=os.path.join(CASES_DIR, "raw_messages.txt"))
    ap.add_argument("--out", default=os.path.join(CASES_DIR, "to_label.jsonl"))
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit(f"找不到 {args.src}，先按 `学员ID|学员原话` 每行一条写好")

    students = read_students()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    n = 0
    with open(args.src, encoding="utf-8") as f, open(args.out, "w", encoding="utf-8") as out:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                raise SystemExit(f"格式不对，应为 `学员ID|原话`：{line}")
            sid, text = [x.strip() for x in line.split("|", 1)]
            if sid not in students:
                raise SystemExit(f"学员 {sid} 不存在，检查 students.json")
            n += 1
            out.write(json.dumps({
                "id": f"E{n:03d}",
                "student_id": sid,
                "kind": "message",
                "text": text,
                "trigger": "",
                "gold_intent": "",
                "gold_mode": "",
                "_stage": students[sid]["stage"],
                "note": "",
            }, ensure_ascii=False) + "\n")

    print(f"已生成 {n} 条待标注样本 → {os.path.relpath(args.out, ROOT)}")
    print("逐个填 gold_intent（null 表示不该进模型）和 gold_mode，")
    print("填完改名 gold.jsonl，跑：python eval/run_eval.py")


if __name__ == "__main__":
    main()
