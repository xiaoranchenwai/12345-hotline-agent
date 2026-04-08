---
name: context-switch
description: 检测到对话中途出现意图切换时，负责保存当前任务上下文、切换到新任务、并在新任务完成后恢复原任务。
---

## 触发条件
- 当前有 ACTIVE 任务，用户新输入检测到不同意图

## 工作流

### 暂停当前任务（PAUSE）
1. 调用要素提取子智能体获取当前要素快照
2. 将完整任务状态序列化存入 session stack
3. 更新 active_task.status = "PAUSED"
4. 增加 interrupt_depth 计数
5. 检查 interrupt_depth，超过 2 则拒绝切换

### 恢复暂停任务（RESUME）
1. 新任务完成后，检查 task_stack 中是否有 PAUSED 任务
2. 从 stack 中取出，恢复为 active_task
3. 减少 interrupt_depth 计数
4. 生成自然的过渡话术

## 过渡话术生成规则
- 先给新任务收尾（一句话确认完成）
- 用"我们继续""接下来""回到刚才"等词自然衔接
- 直接给出下一个问题，不重复已收集的信息
