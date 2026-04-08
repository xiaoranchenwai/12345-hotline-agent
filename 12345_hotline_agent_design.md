# 12345 热线智能客服系统设计文档

> 基于 **DeepAgents** 框架构建，支持本地大模型服务的政务热线智能客服解决方案

---

## 目录

1. [系统概述](#1-系统概述)
2. [整体架构](#2-整体架构)
3. [智能体设计](#3-智能体设计)
   - 3.1 [主智能体（Supervisor Agent）](#31-主智能体supervisor-agent)
   - 3.2 [投诉子智能体（Complaint Agent）](#32-投诉子智能体complaint-agent)
   - 3.3 [要素提取子智能体（Element Extraction Agent）](#33-要素提取子智能体element-extraction-agent)
   - 3.4 [咨询子智能体（Inquiry Agent）](#34-咨询子智能体inquiry-agent)
   - 3.5 [建议子智能体（Suggestion Agent）](#35-建议子智能体suggestion-agent)
4. [AGENTS.md 设计](#4-agentsmd-设计)
5. [Skills 设计](#5-skills-设计)
6. [工程目录结构](#6-工程目录结构)
7. [核心流程说明](#7-核心流程说明)
8. [突发情况处理策略](#8-突发情况处理策略)
9. [对话中途切换场景处理](#9-对话中途切换场景处理)
   - 9.1 [场景一：投诉中途插入咨询](#91-场景一投诉中途插入咨询)
   - 9.2 [场景二：投诉中途新增投诉](#92-场景二投诉中途新增投诉)
   - 9.3 [会话栈状态机设计](#93-会话栈状态机设计)
   - 9.4 [新增 Skills 说明](#94-新增-skills-说明)
   - 9.5 [关键代码示例](#95-关键代码示例)
10. [关键代码示例](#10-关键代码示例)
11. [部署说明](#11-部署说明)

---

## 1. 系统概述

12345 热线智能客服系统旨在通过 AI 自动处理市民的**投诉、咨询和建议**三类诉求，降低人工坐席压力，提升服务响应效率。

### 核心能力

| 能力 | 说明 |
|------|------|
| 意图识别 | 自动判断用户诉求类型（投诉 / 咨询 / 建议） |
| 多轮对话 | 逐步引导用户补充缺失信息，保持对话连贯 |
| 要素提取 | 针对不同投诉类型，自动识别并追问缺失要素 |
| 知识库调用 | 咨询类问题接入政务知识库接口获取权威答案 |
| 突发应对 | 内置异常检测与降级策略，保证服务流畅性 |
| 本地化部署 | 支持对接本地大模型服务（兼容 OpenAI API 格式） |

---

## 2. 整体架构

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│              主智能体（Supervisor Agent）                  │
│  AGENTS.md: supervisor/AGENTS.md                        │
│  Skills: intent-classification, session-management      │
│                                                         │
│  意图分类 → 路由到对应子智能体                             │
└──────────┬──────────────┬──────────────┬────────────────┘
           │              │              │
           ▼              ▼              ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ 投诉子智能体  │ │ 咨询子智能体  │ │ 建议子智能体  │
  │ Complaint    │ │  Inquiry     │ │ Suggestion   │
  │  Agent       │ │   Agent      │ │   Agent      │
  └──────┬───────┘ └──────┬───────┘ └──────────────┘
         │                │
         ▼                ▼
  ┌──────────────┐ ┌──────────────┐
  │ 要素提取     │ │ 知识库接口    │
  │ 子智能体     │ │  Knowledge   │
  │ Element      │ │  Base API    │
  │ Extraction   │ └──────────────┘
  │   Agent      │
  └──────────────┘
         │
         ▼
  ┌──────────────┐
  │ 工单系统接口  │
  │ Ticket API   │
  └──────────────┘
```

### 框架技术栈

```
DeepAgents (LangGraph)
   ├── 本地大模型服务（OpenAI 兼容接口）
   ├── FilesystemBackend（会话上下文持久化）
   ├── AGENTS.md（各智能体身份与指令）
   └── Skills（按需加载的专项技能）
```

---

## 3. 智能体设计

### 3.1 主智能体（Supervisor Agent）

**职责：** 对话入口，负责意图分类和子智能体路由调度，并在子智能体回调后汇总结果返回用户。

**AGENTS.md 核心指令摘要：**

- 保持礼貌、专业、简洁的政务客服口吻
- 分析用户输入，将其分类为：`投诉（COMPLAINT）` / `咨询（INQUIRY）` / `建议（SUGGESTION）`
- 对于模糊意图，通过一次追问确认，禁止多次反复询问同一问题
- 路由决策后，将完整上下文传递给对应子智能体
- 接收子智能体结果并以统一格式呈现给用户

**加载的 Skills：**

| Skill | 触发场景 |
|-------|---------|
| `intent-classification` | 用户首次发言或意图不明确时 |
| `session-management` | 多轮对话上下文切换、会话超时处理 |
| `fallback-handling` | 意图无法识别、系统异常时的降级处理 |

**可调用工具：**

- `spawn_subagent`：调用子智能体
- `write_todos`：规划复杂多步骤任务
- `read_file` / `write_file`：读写会话状态文件

---

### 3.2 投诉子智能体（Complaint Agent）

**职责：** 接管投诉类诉求的完整处理流程，包括类型识别、要素收集、工单生成。

**AGENTS.md 核心指令摘要：**

- 识别投诉子类型（停水 / 停电 / 噪音扰民 / 道路损坏 / 燃气 / 其他）
- 委托**要素提取子智能体**判断当前已收集要素与缺失要素
- 根据缺失要素列表，逐步引导用户补充，每轮只询问一个要素
- 所有必要要素收集完毕后，调用工单接口提交，并给用户反馈工单编号
- 遇到用户情绪激动时，先共情安抚再继续收集

**加载的 Skills：**

| Skill | 触发场景 |
|-------|---------|
| `complaint-type-mapping` | 识别投诉属于哪个子类型及其所需要素清单 |
| `empathy-response` | 用户情绪负面时触发安抚话术 |
| `ticket-submission` | 要素收集完整后，调用工单系统提交 |

**可调用工具：**

- `spawn_subagent(element_extraction_agent)`：调用要素提取子智能体
- `call_ticket_api`：提交工单到业务系统
- `write_todos`：规划多步要素收集任务

**投诉类型与必填要素对照表（示例）：**

```
停水投诉：
  必填 → 用户地址、停水开始时间、是否已恢复
  选填 → 联系电话、影响范围描述

停电投诉：
  必填 → 用户地址、停电开始时间、是否整栋楼停电
  选填 → 联系电话、设备损坏情况

噪音扰民：
  必填 → 噪音来源位置、发生时间段、噪音类型（施工/娱乐/其他）
  选填 → 频次、已自行协商记录

道路损坏：
  必填 → 具体路段或路口、损坏类型（坑洞/护栏/标线）、是否影响通行
  选填 → 照片描述、发现时间
```

---

### 3.3 要素提取子智能体（Element Extraction Agent）

**职责：** 专项分析对话历史，判断已获取的信息要素和仍缺失的要素，输出结构化的要素状态报告，供投诉子智能体驱动下一轮追问。

> 这是系统的关键子智能体，负责确保投诉信息完整性，同时避免重复询问已经提供过的信息。

**AGENTS.md 核心指令摘要：**

- 接收输入：`投诉类型` + `必填要素清单` + `当前对话历史`
- 逐条检查每个必填要素是否已在对话中明确提及
- 对于模糊或不完整的回答（如"昨天"代替具体时间），标记为**待确认**
- 输出结构化 JSON，包含：已收集要素、缺失要素、待确认要素、建议下一问
- 禁止直接与用户对话，只输出分析结果供上层智能体使用

**输出格式规范：**

```json
{
  "complaint_type": "停水投诉",
  "collected": {
    "address": "XX区XX路XX号",
    "start_time": "2024-01-15 08:00"
  },
  "missing": ["is_restored"],
  "ambiguous": {
    "start_time": "用户说'今早'，建议确认具体时间点"
  },
  "next_question": "请问目前停水是否已经恢复？",
  "completion_rate": 0.67,
  "is_complete": false
}
```

**加载的 Skills：**

| Skill | 触发场景 |
|-------|---------|
| `element-schema-lookup` | 根据投诉类型加载对应要素清单 |
| `dialogue-parsing` | 从对话历史中提取已提及的要素值 |
| `ambiguity-detection` | 识别表达模糊的要素并生成确认建议 |

---

### 3.4 咨询子智能体（Inquiry Agent）

**职责：** 处理政策法规、办事流程、服务查询等咨询类问题，优先调用知识库接口获取权威答案。

**AGENTS.md 核心指令摘要：**

- 提取用户咨询的核心关键词，构造知识库查询请求
- 知识库有结果时：整理后以简洁语言向用户呈现，附上来源或办理入口
- 知识库无结果时：使用大模型通用知识回答，并明确告知"以官方最新规定为准"
- 知识库接口超时时：启用降级策略，使用大模型知识兜底并记录日志
- 对于复杂咨询（涉及多个部门），拆分问题分步解答

**加载的 Skills：**

| Skill | 触发场景 |
|-------|---------|
| `knowledge-base-query` | 调用政务知识库接口检索答案 |
| `answer-formatting` | 格式化知识库返回内容，提升可读性 |
| `multi-department-routing` | 问题涉及多部门时的分步解答策略 |

**可调用工具：**

- `call_knowledge_base_api(query, category)`：调用知识库接口
- `write_todos`：复杂咨询的多步分析规划

---

### 3.5 建议子智能体（Suggestion Agent）

**职责：** 接收市民对城市治理、公共服务的改进建议，通过大模型理解和整理建议内容，给予积极回应并记录入库。

**AGENTS.md 核心指令摘要：**

- 认真倾听并感谢市民提出建议
- 使用大模型对建议进行要点提炼和分类（城市建设 / 交通 / 环境 / 教育 / 医疗 / 其他）
- 给予积极、有温度的回应，不做具体承诺但表达重视
- 将整理后的建议摘要提交到建议记录系统
- 若建议明显属于投诉或咨询，礼貌引导转入对应流程

**加载的 Skills：**

| Skill | 触发场景 |
|-------|---------|
| `suggestion-classification` | 对建议内容进行类别标注 |
| `warm-response-generation` | 生成有温度、有情感的正向回应话术 |

---

## 4. AGENTS.md 设计

每个智能体拥有独立的 `AGENTS.md`，以下为各文件的结构规范：

### 主智能体 `supervisor/AGENTS.md`

```markdown
# 12345 热线主智能体

## 角色定位
你是 12345 政务服务热线的智能客服主调度员，负责接待市民，判断其诉求类型，
并将对话路由到最合适的处理流程。

## 行为准则
- 语气：礼貌、温和、专业，使用普通话书面表达
- 每轮回复不超过 150 字，避免冗长
- 意图不明时最多追问一次，仍不明确则默认进入咨询流程
- 禁止承诺具体办理时限或结果

## 意图分类规则
- 包含"投诉""举报""不满""问题""损坏""停止服务"等词 → COMPLAINT
- 包含"怎么办""如何""流程""政策""查询""需要什么"等词 → INQUIRY  
- 包含"建议""希望""改进""能不能""应该"等词 → SUGGESTION
- 歧义或混合意图 → 追问一次确认

## 安全规则
- 不讨论与政务服务无关的话题
- 不评价政府工作的好坏
- 遇到投诉类语言攻击，保持克制并引导回正题
```

### 投诉子智能体 `agents/complaint/AGENTS.md`

```markdown
# 投诉处理子智能体

## 角色定位
你负责处理市民投诉，目标是高效、完整地收集投诉要素，
并生成准确的工单提交到处理系统。

## 收集策略
- 每次只问一个问题，不要一次性列出所有缺失要素
- 用户已提供的信息不重复询问
- 对用户的困扰表示理解，再继续收集
- 超过 3 次无法获取某一要素时，标记为"用户未提供"并继续

## 委托规则
- 每次用户回答后，调用要素提取子智能体分析当前要素完整度
- 根据提取结果决定下一步：继续追问 or 提交工单

## 工单提交规范
提交前向用户确认关键信息，格式：
"我已为您记录以下信息：[摘要]，是否确认提交？"
```

### 要素提取子智能体 `agents/element-extraction/AGENTS.md`

```markdown
# 要素提取分析子智能体

## 角色定位
你是一个信息分析专家，只负责分析对话内容并输出结构化的要素状态报告，
不直接与用户交互。

## 工作方式
1. 接收：投诉类型 + 必填要素清单 + 对话历史
2. 逐一核查每个要素是否已在对话中明确获取
3. 识别表达模糊的要素（如时间说"最近"）
4. 输出标准 JSON 格式报告

## 输出要求
- 必须输出合法 JSON，不输出任何额外文字
- completion_rate 为 0~1 的浮点数
- next_question 为建议的下一个追问语句（中文）
- is_complete 为 true 时表示可以提交工单
```

---

## 5. Skills 设计

Skills 按需加载，以下是主要 Skill 的设计规范：

### `skills/intent-classification/SKILL.md`（主智能体）

```
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
```

### `skills/complaint-type-mapping/SKILL.md`（投诉子智能体）

```
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
2. 加载对应的要素清单（从 data/complaint-schemas.json 读取）
3. 返回结构化的要素需求对象
```

### `skills/knowledge-base-query/SKILL.md`（咨询子智能体）

```
---
name: knowledge-base-query
description: 调用政务知识库 API 检索权威答案，处理返回结果或触发降级策略。
---

## 查询工作流

1. 提取关键词，构造查询参数
2. 调用 call_knowledge_base_api 工具
3. 超时（>3s）→ 降级到大模型通用知识
4. 返回空 → 尝试拆分问题再次查询
5. 成功返回 → 格式化呈现给用户

## 降级策略
- 一级降级：拆分关键词重试
- 二级降级：使用大模型知识回答，添加免责声明
- 三级降级：提示用户拨打人工坐席

## 答案格式化要求
- 不超过 200 字
- 分步骤时使用数字序号
- 附上相关办理窗口或链接（如知识库有提供）
```

### `skills/fallback-handling/SKILL.md`（主智能体）

```
---
name: fallback-handling
description: 处理各类异常情况，包括意图无法识别、子智能体超时、API 调用失败等，
保证对话流畅性和服务可用性。
---

## 异常类型与处理策略

| 异常类型 | 触发条件 | 处理方式 |
|---------|---------|---------|
| 意图不明确 | 两次追问仍无法分类 | 默认进入咨询流程 |
| 子智能体超时 | 响应 >5s | 告知用户"正在处理"，重试一次 |
| 知识库不可用 | API 返回 5xx | 启用大模型兜底，记录错误日志 |
| 工单提交失败 | Ticket API 异常 | 本地保存工单，告知用户稍后重试 |
| 用户情绪激动 | 检测到攻击性语言 | 先安抚，再引导回正题 |
| 对话超时 | 用户超 5 分钟未回复 | 发送提醒，超 10 分钟关闭会话 |
```

---

## 6. 工程目录结构

```
12345-hotline-agent/
├── main.py                          # 系统入口，Web API 或 CLI
├── agents/
│   ├── supervisor/
│   │   └── AGENTS.md                # 主智能体身份与指令
│   ├── complaint/
│   │   └── AGENTS.md                # 投诉子智能体指令
│   ├── element-extraction/
│   │   └── AGENTS.md                # 要素提取子智能体指令
│   ├── inquiry/
│   │   └── AGENTS.md                # 咨询子智能体指令
│   └── suggestion/
│       └── AGENTS.md                # 建议子智能体指令
├── skills/
│   ├── intent-classification/
│   │   └── SKILL.md
│   ├── complaint-type-mapping/
│   │   └── SKILL.md
│   ├── element-schema-lookup/
│   │   └── SKILL.md
│   ├── dialogue-parsing/
│   │   └── SKILL.md
│   ├── knowledge-base-query/
│   │   └── SKILL.md
│   ├── answer-formatting/
│   │   └── SKILL.md
│   ├── empathy-response/
│   │   └── SKILL.md
│   ├── ticket-submission/
│   │   └── SKILL.md
│   ├── session-management/
│   │   └── SKILL.md
│   ├── fallback-handling/
│   │   └── SKILL.md
│   └── warm-response-generation/
│       └── SKILL.md
├── data/
│   ├── complaint-schemas.json        # 各类投诉的要素清单定义
│   └── intent-keywords.json         # 意图分类关键词词典
├── tools/
│   ├── knowledge_base.py            # 知识库 API 调用封装
│   ├── ticket_api.py                # 工单系统 API 调用封装
│   └── session_store.py             # 会话状态存储工具
├── sessions/                        # FilesystemBackend 会话文件目录
├── logs/                            # 系统日志目录
├── .env.example                     # 环境变量模板
├── pyproject.toml                   # 依赖配置
└── README.md                        # 项目说明
```

---

## 7. 核心流程说明

### 7.1 投诉处理完整流程

```
用户: "我家昨晚开始就停水了"
         │
         ▼
主智能体：意图分类 → COMPLAINT（置信度 0.92）
         │
         ▼
主智能体：spawn_subagent(complaint_agent, context)
         │
         ▼
投诉子智能体：识别投诉类型 → WATER_OUTAGE
         │
         ▼
投诉子智能体：spawn_subagent(element_extraction_agent, {
   complaint_type: "WATER_OUTAGE",
   required_elements: ["address", "start_time", "is_restored"],
   dialogue_history: [...]
})
         │
         ▼
要素提取子智能体：分析对话历史
   → collected: { start_time: "昨晚（待确认具体时间）" }
   → missing: ["address", "is_restored"]
   → next_question: "请问您的详细地址是？"
   → is_complete: false
         │
         ▼
投诉子智能体：向用户提问 "请问您的详细地址是？"
用户: "XX区XX路88号"
         │
         ▼
（循环：提取要素 → 追问 → 再提取 → 直至 is_complete: true）
         │
         ▼
投诉子智能体：call_ticket_api(complaint_data)
         │
         ▼
返回用户："您的投诉已登记，工单编号：20240115-00234，
         预计 24 小时内反馈处理进展。"
```

### 7.2 咨询处理流程

```
用户: "办理营业执照需要哪些材料？"
         │
         ▼
主智能体：意图分类 → INQUIRY
         │
         ▼
主智能体：spawn_subagent(inquiry_agent, context)
         │
         ▼
咨询子智能体：提取关键词 ["营业执照", "材料"]
         │
         ▼
咨询子智能体：call_knowledge_base_api("营业执照办理材料")
         ├─ 成功 → 格式化返回答案
         └─ 失败/超时 → 大模型知识兜底 + 免责声明
         │
         ▼
返回用户：整理后的权威答案
```

### 7.3 建议处理流程

```
用户: "建议在XX公园增加健身器材"
         │
         ▼
主智能体：意图分类 → SUGGESTION
         │
         ▼
主智能体：spawn_subagent(suggestion_agent, context)
         │
         ▼
建议子智能体：
   1. 要点提炼 → "XX公园健身设施需求"
   2. 分类标注 → 城市建设 > 公园设施
   3. 生成温暖回应
   4. 提交建议记录系统
         │
         ▼
返回用户："感谢您的宝贵建议！我们已将您关于增设健身设施的建议
         转达至相关部门，您的声音对改善城市服务很有价值。"
```

---

## 8. 突发情况处理策略

### 8.1 用户情绪管理

```
触发条件：检测到强烈负面情绪词汇（愤怒、投诉无用、敷衍等）

处理流程：
  1. empathy-response Skill 生成安抚话术
  2. 暂缓信息收集，优先进行情绪疏导
  3. 情绪稳定后，使用 write_todos 重新规划收集步骤
  4. 若用户持续情绪激动超过 3 轮，提示转接人工坐席

示例话术：
  "非常理解您的不便和困扰，这确实影响了您的正常生活。
   我们一定认真记录并跟进您的问题，请您稍作说明..."
```

### 8.2 信息混乱处理

```
触发条件：用户在一段话中包含多个诉求类型

处理流程：
  1. 主智能体识别到混合意图
  2. 拆分多个诉求，使用 write_todos 规划处理顺序
  3. 优先处理投诉（时效性更强），再处理咨询
  4. 每个诉求独立生成工单或答复

示例：
  用户: "我家停水了，另外想问一下水费怎么查询？"
  处理: 先完成停水投诉要素收集并提交工单，
        再切换到咨询流程回答水费查询问题
```

### 8.3 API 与系统故障降级

```
级别一：知识库 API 超时（>3s）
  → 重试一次，仍失败则使用大模型知识回答
  → 添加声明："以下为参考信息，请以官方最新规定为准"

级别二：工单系统不可用
  → 将完整工单数据写入本地 sessions/ 目录
  → 告知用户："系统繁忙，您的信息已暂存，
    我们将在系统恢复后立即为您提交，请保留对话记录"
  → 触发告警通知运维人员

级别三：主模型服务异常
  → 返回固定应急话术，提示拨打人工热线 12345
  → 记录完整错误日志
```

### 8.4 会话超时管理

```
5 分钟无回复：
  → 发送提醒："您好，请问还在吗？如有需要随时告诉我。"

10 分钟无回复：
  → 保存会话状态到 sessions/ 目录
  → 发送结束语："本次对话已因超时关闭，
    如需继续请重新发起，祝您生活愉快。"

用户重新连接：
  → 从 sessions/ 恢复上次会话状态
  → 提示："欢迎回来，上次您咨询的是[摘要]，是否继续？"
```

---

## 9. 关键代码示例

### 9.1 主智能体创建

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.chat_models import init_chat_model

def create_supervisor_agent():
    model = init_chat_model(
        model="your-local-model",
        model_provider="openai",
        temperature=0,
        base_url="http://localhost:8000/v1",
        api_key="none",
        timeout=30
    )

    agent = create_deep_agent(
        model=model,
        memory=["./agents/supervisor/AGENTS.md"],
        skills=["./skills/"],
        tools=[spawn_complaint_agent, spawn_inquiry_agent, spawn_suggestion_agent],
        subagents=[complaint_agent, inquiry_agent, suggestion_agent],
        backend=FilesystemBackend(root_dir="./sessions")
    )

    return agent
```

### 9.2 要素提取子智能体调用示例

```python
def create_element_extraction_agent():
    model = init_chat_model(...)

    agent = create_deep_agent(
        model=model,
        memory=["./agents/element-extraction/AGENTS.md"],
        skills=[
            "./skills/element-schema-lookup/",
            "./skills/dialogue-parsing/",
            "./skills/ambiguity-detection/"
        ],
        tools=[load_complaint_schema, parse_dialogue],
        subagents=[],
        backend=FilesystemBackend(root_dir="./sessions")
    )

    return agent

# 调用示例
def extract_elements(complaint_type: str, dialogue_history: list) -> dict:
    agent = create_element_extraction_agent()
    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"""
                投诉类型：{complaint_type}
                对话历史：{json.dumps(dialogue_history, ensure_ascii=False)}
                请分析并输出要素状态 JSON。
            """
        }]
    })
    return json.loads(result["messages"][-1].content)
```

### 9.3 知识库工具封装

```python
import httpx
from typing import Optional

async def call_knowledge_base_api(
    query: str,
    category: Optional[str] = None,
    timeout: float = 3.0
) -> dict:
    """
    调用政务知识库接口
    返回格式：{"found": bool, "answer": str, "source": str}
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "http://knowledge-base-service/api/query",
                json={"query": query, "category": category}
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        # 触发降级策略
        return {"found": False, "answer": None, "source": "timeout"}
    except Exception as e:
        return {"found": False, "answer": None, "source": f"error: {str(e)}"}
```

### 9.4 投诉要素清单数据结构（`data/complaint-schemas.json`）

```json
{
  "WATER_OUTAGE": {
    "display_name": "停水投诉",
    "required_elements": [
      {
        "key": "address",
        "label": "详细地址",
        "question": "请问您的详细地址是（精确到楼栋）？",
        "validation": "非空"
      },
      {
        "key": "start_time",
        "label": "停水开始时间",
        "question": "请问大概是从什么时间开始停水的？",
        "validation": "时间格式"
      },
      {
        "key": "is_restored",
        "label": "是否已恢复",
        "question": "请问目前水已经恢复了吗？",
        "validation": "布尔"
      }
    ],
    "optional_elements": [
      {
        "key": "contact_phone",
        "label": "联系电话",
        "question": "方便留一个联系电话，以便后续跟进吗？"
      }
    ]
  }
}
```

---

## 10. 部署说明

### 10.1 环境要求

```
Python >= 3.11
deepagents >= 0.3.5
langchain >= 1.2.3
langchain-community >= 0.3.0
langgraph >= 1.0.6
httpx >= 0.27.0
python-dotenv >= 1.0.0
```

### 10.2 环境变量配置（`.env`）

```bash
# 本地大模型服务
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL_NAME=your-local-model-name
LLM_API_KEY=none

# 知识库服务
KNOWLEDGE_BASE_URL=http://your-kb-service/api
KNOWLEDGE_BASE_TOKEN=your_token

# 工单系统
TICKET_API_URL=http://your-ticket-system/api
TICKET_API_KEY=your_ticket_key

# 会话存储路径
SESSION_DIR=./sessions
LOG_DIR=./logs

# （可选）LangSmith 链路追踪
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=12345-hotline-agent
```

### 10.3 快速启动

```bash
# 1. 克隆项目
git clone https://your-repo/12345-hotline-agent.git
cd 12345-hotline-agent

# 2. 创建虚拟环境并安装依赖
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填写本地模型服务地址和各 API 配置

# 4. 测试运行（CLI 模式）
python main.py --message "我家停水了"

# 5. 启动 Web API（生产模式）
uvicorn main:app --host 0.0.0.0 --port 8080
```

### 10.4 接口示例（Web API）

```bash
# 发起对话
POST /api/chat
Content-Type: application/json

{
  "session_id": "user-12345-abc",
  "message": "我家昨晚停水了"
}

# 响应
{
  "session_id": "user-12345-abc",
  "reply": "非常抱歉给您带来不便！请问您的详细地址是？",
  "intent": "COMPLAINT",
  "complaint_type": "WATER_OUTAGE",
  "completion_rate": 0.0,
  "ticket_id": null
}
```

---

---

## 9. 对话中途切换场景处理

多任务切换是客服对话中最常见的复杂情况。系统采用**会话栈（Session Stack）**机制来管理并发意图，保证每个任务的上下文互不污染，且能在切换后无缝恢复。

### 9.1 场景一：投诉中途插入咨询

#### 场景描述

用户正在进行停水投诉，客服已收集部分要素（如地址），但尚未完成时，用户突然提出一个咨询类问题。系统应**暂停当前投诉流程、处理咨询、然后自动续接未完成的投诉**。

#### 对话示例

```
客服：请问您的详细地址是？
用户：XX区XX路88号。对了，我想问一下停水期间用水怎么申请临时供水？
客服：[先回答咨询] 临时供水申请流程是...
客服：[咨询处理完毕后，自动续接] 好的，您的地址已记录。
      请问停水大约是从什么时间开始的？
```

#### 处理流程

```
用户回复（含咨询插入）
        │
        ▼
主智能体：检测到当前已有活跃投诉任务（stack 非空）
主智能体：同时识别出新意图 → INQUIRY
        │
        ▼
主智能体：调用 context-switch Skill
  ├── 将当前投诉任务状态序列化存入 session stack
  │     {
  │       task_id: "complaint-001",
  │       type: "WATER_OUTAGE",
  │       collected: { address: "XX区XX路88号" },
  │       missing: ["start_time", "is_restored"],
  │       next_question: "请问停水大约从什么时间开始的？",
  │       status: "PAUSED"
  │     }
  └── 标记切换类型为 INQUIRY_INTERRUPT（可恢复型）
        │
        ▼
spawn_subagent(inquiry_agent)：处理咨询问题
        │
        ▼
咨询子智能体完成回答
        │
        ▼
主智能体：检测 stack 顶部有 PAUSED 的投诉任务
主智能体：调用 context-resume Skill
  ├── 从 session stack 恢复投诉上下文
  ├── 生成续接过渡语："好的，您的问题已解答。我们继续刚才的停水投诉——"
  └── 将恢复的 next_question 传递给投诉子智能体
        │
        ▼
投诉子智能体：继续从断点处追问
"请问停水大约是从什么时间开始的？"
```

#### 关键设计原则

| 原则 | 说明 |
|------|------|
| 栈式暂停 | 投诉任务入栈暂停，不丢失任何已收集要素 |
| 自动续接 | 咨询完成后无需用户重新描述投诉，系统主动衔接 |
| 过渡话术 | 续接时使用自然过渡语，避免突兀切换 |
| 单次插入 | 若咨询处理过程中再次出现插入，仅允许嵌套一层，避免无限递归 |

---

### 9.2 场景二：投诉中途新增投诉

#### 场景描述

用户在进行停水投诉的要素收集过程中，突然提出另一个新的投诉（如停电）。两个投诉均需独立建立工单，系统应**分别记录、分别追问、最终各自提交**，避免两个投诉的信息混淆。

#### 对话示例

```
客服：请问停水大约是从什么时间开始的？
用户：昨晚八点。另外我们楼道的灯也坏了好几天了，也要投诉！
客服：好的，两个问题都帮您记录。停水的问题我们继续，
      请问目前停水是否已经恢复？
用户：还没恢复。
客服：停水投诉已为您登记（工单号：A001）。
      接下来我们处理楼道灯损坏的投诉，请问是哪栋楼哪层楼道的灯？
```

#### 处理流程

```
用户回复（含新投诉插入）
        │
        ▼
主智能体：识别到当前有活跃投诉任务（WATER_OUTAGE，进行中）
主智能体：同时识别出新意图 → COMPLAINT（新投诉：楼道灯损坏）
        │
        ▼
主智能体：调用 multi-complaint Skill，执行冲突判断
  ├── 判断新投诉是否与当前投诉属于同一工单（无关联 → 分开处理）
  ├── 生成新投诉任务，加入 session stack，状态为 PENDING
  │     {
  │       task_id: "complaint-002",
  │       type: "FACILITY_DAMAGE",  // 楼道灯
  │       collected: {},
  │       status: "PENDING"
  │     }
  └── 确定处理策略：COMPLETE_CURRENT_FIRST（先完成当前投诉）
        │
        ▼
主智能体：告知用户两个投诉都已记录，当前先完成停水投诉
"好的，两个投诉都帮您记录。我们先把停水的信息补全——"
        │
        ▼
投诉子智能体（WATER_OUTAGE）：继续追问剩余要素
        │ 要素收集完毕
        ▼
call_ticket_api(water_outage_data) → 工单 A001 提交成功
        │
        ▼
主智能体：从 session stack 取出 PENDING 的投诉任务（楼道灯）
主智能体：过渡话术："停水投诉已为您登记（工单号：A001）。
          接下来我们处理楼道灯损坏的投诉——"
        │
        ▼
spawn_subagent(complaint_agent, task=complaint-002)
投诉子智能体（FACILITY_DAMAGE）：重新开始要素收集
        │ 要素收集完毕
        ▼
call_ticket_api(facility_damage_data) → 工单 A002 提交成功
        │
        ▼
主智能体：汇总结果
"两项投诉均已登记：
  ① 停水投诉（工单号：A001）
  ② 楼道灯损坏（工单号：A002）
  预计 24 小时内跟进，感谢您的耐心！"
```

#### 特殊子情况：新投诉与当前投诉高度相关

```
示例：
  用户投诉停水（WATER_OUTAGE），中途说"而且我们小区燃气也停了"

处理策略（SAME_AREA_COMPLAINTS）：
  ├── 识别到同一地址、同一时间段的多个停供投诉
  ├── 询问用户："您的停水和停燃气都发生在 XX 区 XX 路 88 号吗？"
  ├── 若用户确认同一地址：共享地址要素，减少重复追问
  │     → 分别建立工单，但地址/时间等共同要素只问一次
  └── 若涉及不同地址：作为独立投诉分别处理
```

#### 多投诉处理策略对照

| 策略名 | 触发条件 | 处理方式 |
|--------|---------|---------|
| `COMPLETE_CURRENT_FIRST` | 新投诉与当前投诉无关联 | 完成当前投诉后顺序处理新投诉 |
| `SAME_AREA_COMPLAINTS` | 新旧投诉地址/时间相近 | 共享要素，减少重复追问 |
| `INQUIRY_INTERRUPT` | 新意图为咨询 | 暂停投诉，处理咨询，自动续接 |
| `SUGGESTION_DEFER` | 新意图为建议 | 记录建议内容，投诉完成后处理 |

---

### 9.3 会话栈状态机设计

所有中途切换场景的核心是**会话栈（Session Stack）**，由主智能体通过 `FilesystemBackend` 持久化管理。

#### 栈结构定义

```json
{
  "session_id": "user-abc-123",
  "active_task": {
    "task_id": "complaint-001",
    "agent_type": "COMPLAINT",
    "complaint_type": "WATER_OUTAGE",
    "collected": {
      "address": "XX区XX路88号",
      "start_time": "2024-01-15 20:00"
    },
    "missing": ["is_restored"],
    "next_question": "请问目前停水是否已经恢复？",
    "status": "ACTIVE"
  },
  "task_stack": [
    {
      "task_id": "complaint-002",
      "agent_type": "COMPLAINT",
      "complaint_type": "FACILITY_DAMAGE",
      "collected": {},
      "missing": ["location", "damage_type", "duration"],
      "next_question": null,
      "status": "PENDING",
      "created_reason": "USER_INTERRUPT"
    }
  ],
  "completed_tasks": [
    {
      "task_id": "inquiry-001",
      "agent_type": "INQUIRY",
      "query": "停水期间如何申请临时供水",
      "status": "COMPLETED",
      "ticket_id": null
    }
  ],
  "interrupt_depth": 1,
  "last_updated": "2024-01-15T20:30:00Z"
}
```

#### 任务状态流转

```
                    用户提出新任务
                         │
          ┌──────────────┴──────────────┐
          │ 当前任务为 ACTIVE            │
          ▼                             ▼
    新任务为咨询/建议              新任务为投诉
          │                             │
    当前任务 → PAUSED             当前任务保持 ACTIVE
    新任务   → ACTIVE             新任务 → PENDING（入栈）
          │                             │
    [处理咨询/建议]               [完成当前投诉]
          │                             │
    当前任务 → ACTIVE（恢复）      取出栈顶任务 → ACTIVE
          │                             │
          └──────────────┬──────────────┘
                         │
                   任务全部完成
                         │
                  session 状态 → CLOSED
```

#### interrupt_depth 限制

```
规则：interrupt_depth 最大允许值为 2

interrupt_depth = 0：正常对话，无任务切换
interrupt_depth = 1：有一个暂停任务（如咨询打断投诉）
interrupt_depth = 2：有两个待处理任务（投诉 + 投诉 或 投诉 + 咨询）

当 interrupt_depth >= 2 时：
  → 拒绝新的任务插入
  → 回复用户："我看到您有多个问题需要处理，我们一个一个来，
    请先继续当前的问题，完成后再告诉我下一个。"
```

---

### 9.4 新增 Skills 说明

针对以上两个场景，需要在原有 Skills 基础上新增以下专项技能：

#### `skills/context-switch/SKILL.md`（主智能体）

```
---
name: context-switch
description: 检测到对话中途出现意图切换时，负责保存当前任务上下文、
             切换到新任务、并在新任务完成后恢复原任务。
---

## 触发条件
- 当前有 ACTIVE 任务，用户新输入检测到不同意图

## 工作流

### 暂停当前任务（PAUSE）
1. 调用 element_extraction_agent 获取当前要素快照
2. 将完整任务状态序列化写入 session stack 文件
3. 更新 active_task.status = "PAUSED"
4. 增加 interrupt_depth 计数
5. 检查 interrupt_depth，超过 2 则拒绝切换

### 恢复暂停任务（RESUME）
1. 新任务完成后，检查 task_stack 中是否有 PAUSED 任务
2. 从 stack 中取出，恢复为 active_task
3. 减少 interrupt_depth 计数
4. 生成自然的过渡话术：
   - 模板："{新任务完成确认语}。我们继续刚才{任务类型}的问题——{next_question}"
   - 示例："好的，临时供水的申请流程已为您解答。
           我们继续刚才的停水投诉——请问目前停水是否已经恢复？"

## 过渡话术生成规则
- 先给新任务收尾（一句话确认完成）
- 用"我们继续""接下来""回到刚才"等词自然衔接
- 直接给出下一个问题，不重复已收集的信息
```

#### `skills/multi-complaint/SKILL.md`（主智能体 + 投诉子智能体）

```
---
name: multi-complaint
description: 处理同一会话中出现多个投诉的情况，负责冲突判断、要素共享、
             顺序调度和汇总输出。
---

## 触发条件
- 当前有 ACTIVE 投诉任务，用户新输入识别为另一个 COMPLAINT

## 工作流

### 冲突判断
1. 提取两个投诉的地址、时间、类型信息
2. 计算相似度：地址相同且时间相近 → SAME_AREA
3. 否则 → INDEPENDENT

### SAME_AREA 处理
1. 告知用户两个投诉将共享地址等要素
2. 构建共享要素集合，两个工单均引用
3. 分别追问各自独有的要素
4. 分别提交工单，工单中标注"关联投诉"

### INDEPENDENT 处理
1. 将新投诉加入 task_stack，状态 PENDING
2. 先完成当前投诉（current first 策略）
3. 当前工单提交后，自动切换到下一个 PENDING 投诉
4. 每次切换时生成清晰的衔接话术

### 汇总输出
所有投诉完成后，生成汇总确认：
"您本次共提交了 N 项投诉：
  ① [类型]（工单号：XXXX）
  ② [类型]（工单号：XXXX）
  ..."
```

#### 需更新的 `supervisor/AGENTS.md` 补充规则

```markdown
## 中途切换处理规则（新增）

### 咨询插入投诉
- 检测时机：每次用户回复后，先判断是否包含与当前任务无关的新意图
- 判断标准：新意图置信度 > 0.75 且与当前任务类型不同
- 处理：调用 context-switch Skill，暂停当前任务，处理新意图，完成后自动续接
- 禁止：不得丢失任何已收集要素；不得要求用户重述投诉内容

### 投诉插入投诉
- 检测时机：同上
- 处理：调用 multi-complaint Skill，评估关联性后决定处理策略
- 优先级：当前任务优先完成，新投诉进入 PENDING 队列
- 例外：若当前任务已收集所有必填要素（is_complete=true），
        可立即提交当前工单再切换

### interrupt_depth 守卫
- 每次切换前检查 interrupt_depth
- interrupt_depth >= 2 时：拒绝新切换，引导用户按顺序处理
- 回复模板："我注意到您有几个问题要反映，我们逐一处理效率更高，
            请先告诉我 [当前问题的下一个追问]"
```

---

### 9.5 关键代码示例

#### 会话栈管理器

```python
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

class SessionStackManager:
    """
    管理会话中的多任务栈，持久化到 FilesystemBackend 目录
    """

    def __init__(self, session_id: str, session_dir: str = "./sessions"):
        self.session_id = session_id
        self.session_file = Path(session_dir) / f"{session_id}.json"
        self.state = self._load_or_init()

    def _load_or_init(self) -> dict:
        if self.session_file.exists():
            return json.loads(self.session_file.read_text(encoding="utf-8"))
        return {
            "session_id": self.session_id,
            "active_task": None,
            "task_stack": [],
            "completed_tasks": [],
            "interrupt_depth": 0,
            "last_updated": datetime.now().isoformat()
        }

    def _save(self):
        self.state["last_updated"] = datetime.now().isoformat()
        self.session_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def can_interrupt(self) -> bool:
        """检查是否允许新的任务切换"""
        return self.state["interrupt_depth"] < 2

    def pause_active_and_push(self, new_task: dict) -> bool:
        """
        暂停当前活跃任务，将新任务设为活跃（用于 INQUIRY_INTERRUPT）
        """
        if not self.can_interrupt():
            return False
        if self.state["active_task"]:
            self.state["active_task"]["status"] = "PAUSED"
            self.state["task_stack"].append(self.state["active_task"])
        new_task["status"] = "ACTIVE"
        new_task["created_reason"] = "USER_INTERRUPT"
        self.state["active_task"] = new_task
        self.state["interrupt_depth"] += 1
        self._save()
        return True

    def queue_pending(self, new_task: dict) -> bool:
        """
        保持当前任务活跃，将新投诉任务加入 PENDING 队列
        （用于 COMPLAINT 中途新增 COMPLAINT）
        """
        if not self.can_interrupt():
            return False
        new_task["status"] = "PENDING"
        new_task["created_reason"] = "USER_INTERRUPT"
        self.state["task_stack"].append(new_task)
        self.state["interrupt_depth"] += 1
        self._save()
        return True

    def complete_active_and_resume(self, ticket_id: Optional[str] = None) -> Optional[dict]:
        """
        完成当前活跃任务，从栈中恢复下一个任务
        """
        if self.state["active_task"]:
            completed = self.state["active_task"]
            completed["status"] = "COMPLETED"
            if ticket_id:
                completed["ticket_id"] = ticket_id
            self.state["completed_tasks"].append(completed)
            self.state["active_task"] = None

        # 从栈中取出下一个任务
        if self.state["task_stack"]:
            next_task = self.state["task_stack"].pop()
            next_task["status"] = "ACTIVE"
            self.state["active_task"] = next_task
            self.state["interrupt_depth"] = max(0, self.state["interrupt_depth"] - 1)
            self._save()
            return next_task

        self._save()
        return None  # 所有任务完成

    def get_resume_transition(self, completed_task: dict, next_task: dict) -> str:
        """
        生成任务切换时的自然过渡话术
        """
        task_type_labels = {
            "INQUIRY": "咨询",
            "COMPLAINT": "投诉",
            "SUGGESTION": "建议"
        }
        completed_label = task_type_labels.get(completed_task["agent_type"], "问题")
        next_label = task_type_labels.get(next_task["agent_type"], "问题")

        if completed_task["agent_type"] == "INQUIRY":
            return (
                f"好的，以上是关于"{completed_task.get('query', '您咨询的问题')}"的解答。"
                f"我们继续刚才的{next_label}——{next_task.get('next_question', '')}"
            )
        elif completed_task["agent_type"] == "COMPLAINT":
            ticket_id = completed_task.get("ticket_id", "处理中")
            return (
                f"{completed_task.get('display_name', next_label)}已为您登记"
                f"（工单号：{ticket_id}）。"
                f"接下来我们处理{next_label}的问题——{next_task.get('next_question', '')}"
            )
        return f"好的，{completed_label}已处理完毕。我们继续——{next_task.get('next_question', '')}"
```

#### 主智能体中的切换检测工具

```python
def detect_intent_switch(
    current_task: dict,
    user_message: str,
    intent_result: dict
) -> dict:
    """
    检测用户输入是否包含意图切换，返回切换建议

    返回格式：
    {
      "should_switch": bool,
      "switch_type": "INQUIRY_INTERRUPT" | "COMPLAINT_QUEUE" | "NONE",
      "new_intent": "COMPLAINT" | "INQUIRY" | "SUGGESTION" | None,
      "reason": str
    }
    """
    current_type = current_task.get("agent_type")
    new_intent = intent_result.get("intent")
    confidence = intent_result.get("confidence", 0)

    # 置信度不足，不切换
    if confidence < 0.75:
        return {"should_switch": False, "switch_type": "NONE",
                "new_intent": None, "reason": "低置信度"}

    # 相同意图，不切换
    if new_intent == current_type:
        return {"should_switch": False, "switch_type": "NONE",
                "new_intent": None, "reason": "相同意图"}

    # 咨询/建议打断投诉 → 可恢复型暂停
    if current_type == "COMPLAINT" and new_intent in ("INQUIRY", "SUGGESTION"):
        return {
            "should_switch": True,
            "switch_type": "INQUIRY_INTERRUPT",
            "new_intent": new_intent,
            "reason": f"投诉中途插入{new_intent}"
        }

    # 新投诉打断当前投诉 → 队列型
    if current_type == "COMPLAINT" and new_intent == "COMPLAINT":
        return {
            "should_switch": True,
            "switch_type": "COMPLAINT_QUEUE",
            "new_intent": "COMPLAINT",
            "reason": "多投诉并发"
        }

    return {"should_switch": False, "switch_type": "NONE",
            "new_intent": None, "reason": "未匹配切换规则"}
```

---

