---
name: bug-fix
description: |
  硅谷 prod 告警批量自动修复工作流。
  扫描飞书告警消息（上限 100 条，遇到已处理消息停止），匹配多维表格历史参考，
  为每条 new_issue 直接启动 1 个 general-purpose Worker（background + worktree），
  每个 Worker 独立完成：CLS 查询 → AI 诊断 → 修复 → 飞书回复 → bitable 写入。
  支持断点续传：会话中断后重新执行时自动从上次完成的 Phase 续传。

  **触发场景：**
  - 执行 /bug-fix 命令
  - 需要批量修复硅谷 prod 环境的线上问题

  **依赖的 Agent Types：**
  general-purpose（每条 issue 独立 1 个 Worker，最多 50 个）

  **依赖的 Skills：**
  worker-fix-java

  **MCP 依赖：** `mcp__lark-mcp__bitable_v1_appTableRecord_create`（bitable 403 fallback，useUAT=true）
---

# bug-fix

## 架构

```
/bug-fix
  ├── Phase 0: 续传检测 → git fetch origin master → 写 state(phase=0)
  ├── Phase 1: pipeline.py（扫描 + bitable + CLS并发 + 三层去重 + triage）→ 写 state(phase=1.7)
  ├── Phase 2: batch_reply.py（非 actionable 消息批量飞书话题回复）→ 写 state(phase=2)
  ├── Phase 3: 启动 Worker（background + worktree）→ 写 state(phase=3)
  ├── Phase 4: 等待 Worker 完成 → 汇总 → round-summary.json
  ├── Phase 4.5: 补偿 Worker（飞书回复 + bitable 写入缺失的）
  └── Phase 5: self_upgrade.py → 删除 state 文件
```

Worker 在 worktree 中工作，不影响主仓库和用户 IDE。

## 飞书回复规则

- **消息回复** `im_v1_message_reply`：`reply_in_thread: true`，**不传 `useUAT`**
- **Bitable 操作** `bitable_v1_appTableRecord_*`：传 `useUAT=true`
- **标题前缀**：⏳等待合并 / ⏳处理中 / ℹ️业务预期 / 🔌外部依赖 / ⚠️无法追踪 / 🔧基础设施问题

---

## 执行流程

### Phase 0: 初始化

**0-A：续传检测**

检查 `/tmp/bugfix/orchestrator-state.json`：
- `phase_completed == 3` → 跳到 Phase 4
- `phase_completed == 2` → 跳到 Phase 3
- `phase_completed == 1.7` → 跳到 Phase 2
- 其他/不存在 → 正常流程

**0-B：初始化**

1. `source ~/Desktop/workspace/claude-code-deploy/scripts/.env` 加载环境变量
2. `cd $MONOREPO_DIR`（确保 worktree 可用）
3. `git fetch origin master`
4. 创建工作目录 `/tmp/bugfix/${ROUND}/`

**0-C：写 state（phase_completed=0）**

---

### Phase 1: pipeline.py

```bash
python3 $SCRIPTS/pipeline.py --target-count 100 --output-dir ${ROUND_DIR} 2>&1
```

输出：scan-result.json、dedup-result.json、cls-results.json、precheck-result.json、duplicate-mapping.json

**Phase 1 完成后**：为每条 duplicate issue 生成 fix-result.json，写 state（phase_completed=1.7）。

actionable_issues 为空 → 跳过 Phase 3，直接 Phase 4。

---

### Phase 2: batch_reply.py

```bash
python3 $SCRIPTS/batch_reply.py --round-dir ${ROUND_DIR} 2>&1
```

为所有非 actionable 消息发送飞书话题回复（duplicates、skipped_triage、skipped_no_trace、scan duplicate_msgs）。写 state（phase_completed=2）。

---

### Phase 3: 启动 Worker

1. 确认 cwd 在 `$MONOREPO_DIR` 内
2. 为每条 actionable issue 启动 1 个 `general-purpose` Agent：
   - `background=true`、`isolation="worktree"`、`bypassPermissions`
   - **禁止回退到非 worktree 模式** — worktree 失败则记录错误跳过，不在主仓库操作

**Worker Prompt**：

```
你是单条 issue 修复 Worker。
issue = {issue_json}
issue_dir = {ROUND_DIR}/issues/{issue_id}/
SCRIPTS = {SCRIPTS_DIR}
duplicate_message_ids = {duplicate_message_ids_json}
bitable_refs = {bitable_refs_json}
cls_result = {cls_result_json}

source ~/Desktop/workspace/claude-code-deploy/scripts/.env
参数: skip_thread_reply=false, skip_feishu_write=false

按 worker-fix-java skill 执行 Step 1-5：
Step 1: 读取 cls_result（已预注入）→ 链路分析
Step 2: AI 诊断根因
Step 2.5: 修复策略决策
Step 3: 修复代码 → 编译 → 提交 → 推送
Step 4: 飞书话题回复（ToolSearch "+lark message reply"，reply_in_thread=true，不传 useUAT）
Step 5: bitable 写入（ToolSearch "+lark bitable record create"，useUAT=true）
Step 6: 回复 duplicate_message_ids（可选）

禁止 git force 操作。禁止合并到 master。全程中文。
```

**数据生成规则**：
- `cls_result` = `cls_results["results"][issue_id]`
- `bitable_refs` = `precheck_result["bitable_refs"].get(issue_id, [])`
- `duplicate_message_ids` = `duplicate_mapping.get(issue_id, [])`

写 state（phase_completed=3）。

---

### Phase 4: 等待 Worker + 汇总

指数退避轮询（15s → 30s → 60s），总超时 20 分钟。全部完成后汇总 round-summary.json + worker-results.json。

---

### Phase 4.5: 补偿 Worker

检查 reply_status / bitable_status 缺失的 issue，启动 1 个补偿 Worker 批量处理。

---

### Phase 5: 分析报告

`python3 $SCRIPTS/self_upgrade.py --round-dir ${ROUND_DIR}`，只汇报建议不自动修改规则。完成后删除 state 文件。

---

## 关键约束

- 禁止所有 git force 操作
- 禁止 stash 用户代码
- Worker 使用 worktree 隔离，不影响主仓库
- Orchestrator 不直接修改代码，不直接调飞书回复 MCP
- 全程输出中文
