---
name: intent-classification
description: 对用户的自然语言输入进行三分类（投诉/咨询/建议），用于主智能体路由决策。
---

## 分类工作流

1. 提取用户输入中的关键词和情感倾向
2. 匹配分类规则（见 AGENTS.md 意图分类规则）
3. 置信度低于 0.7 时触发一次确认追问
4. 输出分类结果和置信度

## 输出格式

{
  "intent": "COMPLAINT | INQUIRY | SUGGESTION",
  "confidence": 0.0~1.0,
  "keywords": ["关键词列表"],
  "need_clarification": true/false,
  "clarification_question": "追问内容（如需）"
}

## 分类参考词典
- COMPLAINT: 投诉、举报、不满、问题、损坏、停水、停电、噪音、扰民
- INQUIRY: 怎么办、如何、流程、政策、查询、需要什么、办理
- SUGGESTION: 建议、希望、改进、能不能、应该
