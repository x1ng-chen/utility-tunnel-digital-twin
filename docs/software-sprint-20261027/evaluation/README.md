# 实际模型与仿真执行记录

下表为真实请求生命周期统计，**不是人工事实准确率或获奖效果证明**。原始响应、失败、工具轨迹和固定数据包见 `actual-traces.zip`，散列见 `manifest.json`。

| 批次 | 方式 | 记录数 | 状态统计 | 模型请求次数（含失败） | 已知Token | 耗时中位数 ms |
|---|---|---:|---|---:|---:|---:|
| 20261027T013401Z-composite-paired.jsonl | multi | 12 | {"completed": 4, "failed": 7, "SERVER_PERMISSION_REJECTED": 1} | 19 | 142207 | 3079 |
| 20261027T013401Z-composite-paired.jsonl | single | 12 | {"completed": 5, "failed": 6, "SERVER_PERMISSION_REJECTED": 1} | 17 | 115572 | 6547 |
| 20261027T013401Z-plain.jsonl | ordinary_model | 12 | {"failed": 12} | 12 | 0 | 1289.0 |
| 20261027T013613Z-regression-multi.jsonl | multi | 30 | {"failed": 28, "SERVER_PERMISSION_REJECTED": 2} | 31 | 6480 | 1109.0 |
| 20261026T183919Z-composite-multi.jsonl | multi | 1 | {"failed": 1} | 5 | 81187 | 19937 |
| 20261027T004846Z-composite-multi.jsonl | multi | 1 | {"completed": 1} | 9 | 263177 | 41766 |
| 20261027T005814Z-composite-paired.jsonl | multi | 12 | {"completed": 10, "failed": 1, "SERVER_PERMISSION_REJECTED": 1} | 56 | 995549 | 18578 |
| 20261027T005814Z-composite-paired.jsonl | single | 12 | {"completed": 10, "failed": 1, "SERVER_PERMISSION_REJECTED": 1} | 30 | 485339 | 8266 |
| 20261027T005814Z-plain.jsonl | ordinary_model | 12 | {"completed": 12} | 12 | 589124 | 11273.0 |
| 20261027T010350Z-regression-multi.jsonl | multi | 30 | {"completed": 19, "failed": 9, "SERVER_PERMISSION_REJECTED": 2} | 170 | 2995711 | 25039.0 |
| 20261027T011647Z-composite-paired.jsonl | multi | 12 | {"completed": 10, "failed": 1, "SERVER_PERMISSION_REJECTED": 1} | 57 | 1114011 | 14891 |
| 20261027T011647Z-composite-paired.jsonl | single | 12 | {"completed": 11, "SERVER_PERMISSION_REJECTED": 1} | 27 | 345413 | 10657 |
| 20261027T012319Z-regression-multi.jsonl | multi | 30 | {"completed": 15, "failed": 13, "SERVER_PERMISSION_REJECTED": 2} | 165 | 3592308 | 30328.0 |

首次失败和修订后重测分批保留。人工组与人工评分未运行；模板见 `human-scoring.csv`。回执为模拟，不能计入真机通过。

普通问答不使用工具；读取同批原始数据包和手册。单/三Agent有同一总预算；简单巡检只取证，复杂任务才运行三个角色。
独立复核结果与任务完成度另见 `summary.json`。成本不按猜测单价推算，实际账单仍待核对。
