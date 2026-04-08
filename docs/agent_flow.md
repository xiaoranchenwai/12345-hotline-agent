# 12345 热线智能客服工程流程说明

本文档基于当前工程代码、`AGENTS.md` 规则文件、各子智能体提示词与技能配置整理，说明系统从入口接收用户消息，到主智能体路由，再到投诉、咨询、建议处理的整体流程。

## 1. 工程目标

该工程实现了一个 12345 政务服务热线智能客服主智能体，负责完成三类任务：

- 投诉类诉求的识别、要素收集与工单提交
- 咨询类诉求的知识库查询与兜底回答
- 建议类诉求的提炼、分类与记录回应

系统当前提供三种入口：

- CLI 单次调用
- CLI 多轮对话
- FastAPI `/api/chat`
- Gradio Web 对话界面

## 2. 核心组件

### 2.1 主智能体

主智能体由 `create_supervisor_agent()` 创建，职责是：

- 读取根目录 `AGENTS.md` 作为记忆与总规则
- 加载意图分类、兜底处理、上下文切换、多投诉处理等技能
- 根据用户输入将任务路由到投诉、咨询、建议子智能体

### 2.2 子智能体

系统定义了三个业务子智能体：

- `complaint_agent`：处理投诉、收集要素、提交工单
- `inquiry_agent`：处理政策与流程咨询，优先调用知识库
- `suggestion_agent`：处理建议，做摘要与温和回应

代码中还预留了 `element_extraction_agent` 规格，用于投诉要素完整度分析；从工程结构看，这是投诉流程中的辅助分析角色。

### 2.3 工具层

当前项目注册了两个主要工具：

- `query_knowledge_base`：查询政务知识库，支持 mock 数据
- `submit_ticket`：提交投诉工单，支持 mock 落盘到 `sessions/`

### 2.4 会话状态层

`tools/session_store.py` 提供多任务栈管理能力，用于支持：

- 咨询插入投诉时的暂停与恢复
- 投诉中再次出现新投诉时的排队处理
- `interrupt_depth` 守卫

从当前代码实现看，主会话历史主要保存在内存列表中，任务栈能力已经具备，但尚未在 `main.py` 中完全串接成显式流程。

## 3. 总体执行流程

```mermaid
flowchart TD
    A[用户输入] --> B{入口类型}
    B -->|CLI 单次| C[run_cli -> _process_single]
    B -->|CLI 多轮| D[run_cli -> _run_interactive]
    B -->|FastAPI| E[POST /api/chat]
    B -->|Gradio| F[gradio chat 回调]

    C --> G[create_supervisor_agent]
    D --> G
    E --> G
    F --> G

    G --> H[create_deep_agent 创建主智能体]
    H --> I[agent.invoke with messages]
    I --> J[主智能体读取 AGENTS.md 与 skills]
    J --> K{识别意图}

    K -->|COMPLAINT| L[路由到 complaint_agent]
    K -->|INQUIRY| M[路由到 inquiry_agent]
    K -->|SUGGESTION| N[路由到 suggestion_agent]
    K -->|低置信度| O[追问一次澄清]

    L --> P[生成回复或提交工单]
    M --> Q[知识库查询或模型兜底]
    N --> R[建议提炼与回应]
    O --> S[进入下一轮消息]

    P --> T[返回最终回复]
    Q --> T
    R --> T
    S --> T
```

## 4. 主智能体路由流程

主智能体是整个工程的调度中心。它先读取根规则，再根据技能完成意图判断。

### 4.1 输入处理

无论来自 CLI、API 还是 Gradio，最终都会构造成统一的消息结构：

```python
{"messages": [{"role": "user", "content": "..."}]}
```

多轮对话模式下，历史消息会持续追加，作为后续轮次的上下文。

### 4.2 意图分类规则

主智能体依据根 `AGENTS.md` 和 `skills/intent-classification` 中的规则进行三分类：

- 包含“投诉、举报、不满、损坏、停水、停电”等词，倾向 `COMPLAINT`
- 包含“怎么办、如何、流程、政策、查询”等词，倾向 `INQUIRY`
- 包含“建议、希望、改进、能不能”等词，倾向 `SUGGESTION`

如果分类置信度不足，则最多追问一次。仍不明确时，规则要求默认进入咨询流程。

```mermaid
flowchart TD
    A[主智能体收到用户消息] --> B[提取关键词与语义信号]
    B --> C{置信度是否 >= 0.7}
    C -->|否| D[追问一次确认]
    C -->|是| E{意图类型}
    D --> F{仍不明确?}
    F -->|是| G[默认进入咨询流程]
    F -->|否| E
    E -->|COMPLAINT| H[投诉子智能体]
    E -->|INQUIRY| I[咨询子智能体]
    E -->|SUGGESTION| J[建议子智能体]
```

## 5. 投诉处理流程

投诉流程是系统最复杂的部分。其目标不是一次性回答，而是逐轮收集必填要素，最后调用工单工具提交。

### 5.1 处理目标

投诉子智能体需要完成以下任务：

- 识别投诉子类型
- 尽量从用户原话中提取已提供信息
- 每轮只追问一个缺失要素
- 全部必填要素收集完成后确认并提交

### 5.2 投诉子类型

当前规则支持：

- `WATER_OUTAGE`
- `POWER_OUTAGE`
- `NOISE_COMPLAINT`
- `ROAD_DAMAGE`
- `GAS_ISSUE`
- `OTHER`

### 5.3 要素清单

`data/complaint_schemas.json` 作为投诉类型到要素清单的配置来源，在技能规则里用于：

- 根据投诉内容映射投诉类型
- 加载该类型的 `required_elements`
- 决定下一轮应追问哪个字段

需要说明的是：当前工程代码中尚未看到显式的 Python 读取逻辑，现阶段主要由技能与提示词层消费这份配置。

### 5.4 工单流程图

```mermaid
flowchart TD
    A[用户投诉] --> B[识别投诉子类型]
    B --> C[加载该类型要素清单]
    C --> D[分析当前消息中已提供的要素]
    D --> E{是否还有缺失必填项}
    E -->|是| F[共情后只追问 1 个缺失要素]
    F --> G[用户补充信息]
    G --> D
    E -->|否| H[汇总关键信息并请求确认]
    H --> I{用户确认提交?}
    I -->|否| J[继续修正信息]
    J --> D
    I -->|是| K[调用 submit_ticket]
    K --> L{提交成功?}
    L -->|是| M[返回工单号]
    L -->|否| N[本地落盘保存并返回失败说明]
```

## 6. 咨询处理流程

咨询子智能体优先调用知识库工具，不直接承诺最终办理结果。

实际处理逻辑如下：

- 提炼咨询关键词
- 调用 `query_knowledge_base`
- 若知识库命中，则整理答案并附来源
- 若未命中或超时，则使用模型知识兜底，并附“以官方最新规定为准”声明

```mermaid
flowchart TD
    A[用户咨询] --> B[提取问题关键词]
    B --> C[调用 query_knowledge_base]
    C --> D{知识库是否命中}
    D -->|是| E[整理答案并附来源]
    D -->|否| F[大模型知识兜底]
    F --> G[附加免责声明]
    E --> H[返回用户]
    G --> H
```

## 7. 建议处理流程

建议子智能体处理相对简单，重点是礼貌、提炼与不承诺。

主要步骤：

- 感谢用户提出建议
- 提炼建议要点
- 做主题分类
- 返回积极、克制的回应

如果建议内容实际上更像投诉或咨询，规则允许将其纠正并转入对应流程。

## 8. 中途切换与多任务管理

工程规则中定义了会话内任务切换机制，这部分由根 `AGENTS.md`、`context-switch` skill 和 `SessionStackManager` 共同支持。

### 8.1 咨询插入投诉

当当前任务不是投诉，用户中途提出高置信度投诉时：

- 暂停当前任务
- 保存当前任务上下文
- 切换到投诉流程
- 投诉完成后恢复之前任务

### 8.2 投诉中新增投诉

当当前已在处理投诉，用户又提出新的投诉时：

- 若与当前投诉关联度高，可共享部分要素
- 若独立，则进入 `PENDING` 队列
- 先完成当前投诉，再恢复排队投诉

### 8.3 interrupt_depth 守卫

为避免无限嵌套切换，系统设置：

- `interrupt_depth < 2`：允许切换
- `interrupt_depth >= 2`：拒绝继续切换，引导用户先完成当前问题

```mermaid
flowchart TD
    A[当前存在 ACTIVE 任务] --> B[检测用户是否提出新意图]
    B --> C{新意图置信度 > 0.75 且类型不同?}
    C -->|否| D[继续当前流程]
    C -->|是| E{interrupt_depth < 2?}
    E -->|否| F[拒绝切换并提示按顺序处理]
    E -->|是| G{当前是投诉且新意图也是投诉?}
    G -->|是| H[进入 multi-complaint 流程]
    G -->|否| I[进入 context-switch 流程]
    I --> J[暂停当前任务并切换]
    H --> K[当前投诉优先，新投诉排队或共享要素]
```

## 9. 工程中的实际落地情况

从当前仓库代码看，可以将流程分成“已直接落地”和“规则已定义但串接仍待加强”两部分。

### 9.1 已直接落地

- 多入口统一汇总到主智能体
- 主智能体通过 `create_deep_agent` 创建
- 咨询、投诉、建议三个子智能体已注册
- 知识库查询工具与工单提交工具可用
- Gradio 与 FastAPI 均支持多轮会话

### 9.2 已有规则但仍偏提示词驱动

- `complaint_schemas.json` 目前主要由技能规则使用
- `element_extraction_agent` 已定义规格，但未在主流程代码中直接实例化
- `SessionStackManager` 已实现，但未在 `main.py` 中显式接入
- 上下文切换和多投诉能力更多依赖 Deep Agent 提示词与技能执行

## 10. 一次典型请求的时序示意

```mermaid
sequenceDiagram
    participant U as 用户
    participant Entry as CLI/API/Gradio
    participant S as Supervisor Agent
    participant C as Complaint/Inquiry/Suggestion Agent
    participant T as Tool

    U->>Entry: 输入诉求
    Entry->>S: 传入 messages
    S->>S: 读取 AGENTS.md 与技能规则
    S->>S: 识别意图
    S->>C: 路由到匹配子智能体
    C->>C: 生成处理策略
    alt 咨询
        C->>T: query_knowledge_base
        T-->>C: 返回答案
    else 投诉
        C->>C: 识别类型并收集要素
        C->>T: submit_ticket
        T-->>C: 返回工单号或失败结果
    else 建议
        C->>C: 提炼与分类建议
    end
    C-->>S: 返回处理结果
    S-->>Entry: 最终回复
    Entry-->>U: 展示回复
```

## 11. 总结

当前工程已经形成了“主智能体调度 + 三类业务子智能体 + 工具层 + 会话状态层”的完整骨架。

如果从工程成熟度看：

- 用户入口、主路由和基础工具已经具备
- 投诉要素清单、任务切换和多投诉策略已经有较完整的规则设计
- 下一步若要增强可控性，应将投诉要素校验、任务栈切换、要素提取等逻辑从提示词层进一步下沉到显式 Python 代码中

