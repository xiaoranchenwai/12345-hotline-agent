---
name: complaint-type-mapping
description: 根据投诉内容识别具体的投诉子类型，并返回对应的必填/选填要素清单。
---

## 支持的投诉子类型
- WATER_OUTAGE（停水）
- POWER_OUTAGE（停电）
- NOISE_COMPLAINT（噪音扰民）
- ROAD_DAMAGE（道路损坏）
- GAS_ISSUE（燃气问题）
- OTHER（其他）

## 工作流
1. 分析投诉描述，匹配最近似的子类型
2. 从 data/complaint_schemas.json 加载对应的要素清单
3. 返回结构化的要素需求对象

## 关键词到类型映射
- 停水/没水/水管/自来水 → WATER_OUTAGE
- 停电/没电/跳闸/电力 → POWER_OUTAGE
- 噪音/吵/扰民/施工噪声 → NOISE_COMPLAINT
- 路面/坑洞/道路/护栏/路灯 → ROAD_DAMAGE
- 燃气/天然气/煤气/停气 → GAS_ISSUE
- 以上均不匹配 → OTHER
