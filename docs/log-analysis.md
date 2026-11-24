# 对话日志分析手册

每次决策都会在 `agent.db` 的 `trace_log` 表留一行——怎么调的、怎么判的、
模型说了什么，全部可查。查看入口三个：

1. **工作台「数据管理」→ 对话日志**：表格浏览，点任意一条看完整明细（含模型 prompt 与回复）
2. **DB Browser for SQLite** 打开 `data/agent.db`，对 `trace_log` 跑 SQL
3. 命令行：`sqlite3 data/agent.db "SELECT ..."`（或 Python）

## 表结构速查

| 字段 | 含义 |
|---|---|
| ts / source | 时间；`demo`=工作台与命令行，`eval`=评估回放 |
| student_id / student / stage | 哪个学员、当时什么阶段 |
| event | message（学员主动）或 timer（主动推送） |
| intent / confidence | 判出的意图与把握度 |
| mode / card / freedom | 策略档位、命中的话术卡片、自由度 |
| reason | 策略层的决策依据（为什么是这个档位） |
| draft | 生成的最终文本 |
| guard | 风控结论（通过 / 拦截原因 / 静默降级） |
| blocked | 拦截原因（非空 = 这条没发出去） |
| touch_count / next_stage / next_goal | 回写后的状态 |
| llm_calls | JSON 数组：每次模型调用的 system / user / response / 耗时 / 是否成功 |

## 常用分析 SQL

**1. 各档位分布（自动处理率是多少）**
```sql
SELECT mode, COUNT(*) FROM trace_log GROUP BY mode ORDER BY 2 DESC;
```

**2. 转人工都在转什么（人工队列的构成）**
```sql
SELECT intent, COUNT(*) FROM trace_log
WHERE mode = 'HUMAN' GROUP BY intent ORDER BY 2 DESC;
```

**3. 被拦截的消息都是为什么**
```sql
SELECT blocked, COUNT(*) FROM trace_log
WHERE blocked <> '' GROUP BY blocked ORDER BY 2 DESC;
```

**4. 每个学员的完整轨迹（复盘一次转化）**
```sql
SELECT ts, event, intent, confidence, mode, card, blocked
FROM trace_log WHERE student_id = 'S002' ORDER BY id;
```

**5. 低置信度样本（该补关键词 / 该标评估集的素材）**
```sql
SELECT ts, student_id, intent, confidence, mode
FROM trace_log WHERE confidence < 0.8 ORDER BY confidence LIMIT 20;
```

**6. 模型调用的耗时与失败率（接真模型后看这个）**
```sql
SELECT source,
       SUM(json_array_length(llm_calls))                  AS 调用次数,
       AVG(json_extract(llm_calls, '$[0].elapsed_ms'))    AS 首次调用耗时ms
FROM trace_log GROUP BY source;
```

**7. 按意图看平均置信度（哪些意图模型最没底）**
```sql
SELECT intent, COUNT(*), ROUND(AVG(confidence), 2)
FROM trace_log WHERE intent <> '' GROUP BY intent ORDER BY 3;
```

**8. 评估与演示对比（接真模型前后各跑一次评估）**
```sql
SELECT source, mode, COUNT(*) FROM trace_log
WHERE source IN ('demo', 'eval') GROUP BY source, mode;
```

## 注意

- `llm_calls` 里 prompt 截断到 400 字符——够定位问题，但别当语料库用；要全量留痕是生产化的事
- 日志会无限增长，定期 `DELETE FROM trace_log WHERE ts < '某日期'` 或直接用工作台的清空按钮
- `trace.jsonl` 仍保留（文件形态方便直接看），内容与库中一致
