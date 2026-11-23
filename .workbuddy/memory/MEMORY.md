# 项目长期记忆 · AI 督学 Agent

## 定位
教育私域转化的「受约束 Agent」demo。**同时是用户的简历代表作**，任何改动优先服务于「可讲清、可度量」，而不是堆功能。

## 架构要点（改动前必读）
- 七层：gate → 上下文装配 → router → policy → executor → guard → trace/回写，串在 `agent/pipeline.py:run()`。
- 策略内核：`policy.MATRIX`，路由键 `(Stage, 意图)` 复合键，值 = (mode, card_id, freedom, extra)。
- 模型只介入两处：`router.classify`（temp=0，json_mode=True）、`executor.execute`（mid/high 自由度润色）。**这个分级是产品设计，不要改。**
- 四档权限 AUTO / CONFIRM / HUMAN / STOP。硬规则：NEVER_AUTO、负面情绪升档、Stage 自由度封顶、置信度<0.75 转人工、无卡片不说话。
- 状态：`agent/store.py` 进程内持有，`get()` 返副本、`commit()` 落库。生产换 DB 时只改这一层。
- 学员状态字段含 `paid_deposit`（订金）与 `paid_final`（尾款），D5→DONE 只看 `paid_final`。

## 已修缺陷（勿回退）
状态回写、LLM json_mode 分离、补「转化铺垫/尾款提醒」意图（共 11 类）、静默时段只拦推送、金额正则收窄、频控单一来源、D5 归档判据、HUMAN/STOP 也写 blocked。

## 已知短板（按优先级，尚未做）
1. **没有评估集与离线回放** —— 最大短板，简历的命门。
2. 置信度是模型自评，未校准；0.75 阈值是拍的。
3. 没有多轮对话上下文，每条消息独立判意图。
4. 风控只有正则，抓不到 high 自由度下的事实性捏造。
5. 工具调用是 mock，无参数抽取、无幂等。
6. `MATRIX` 仍在 Python 里硬编码，README 宣称的"配置化"未落地。
7. 无 token/延迟记录，无法算成本。

## 环境
Python 3.13。已装 streamlit 1.67.0 / pandas 3.1.1（2026-11-24）。
启动：`python cli.py` / `streamlit run app.py`。演示时刻固定 `DEMO_NOW = 19:30`，否则被静默时段规则全拦。
