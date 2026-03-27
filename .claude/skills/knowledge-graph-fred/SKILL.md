# knowledge-graph-fred — 功能知识图谱

## 描述
记录和查询"哪个文件/API 被谁改过"，跨任务积累上下文。支持多项目，按项目隔离。

## 触发场景
- `linear-dev-fred` Phase 1/3 自动调用（查询）
- `linear-dev-fred` Phase 7 自动调用（写入）
- 用户直接问"xxx 文件之前改过什么"或"xxx API 的历史"

## 存储
- 按项目隔离: `~/.claude/knowledge-graph/<project>/graph.json`
- 项目名（project slug）从 repo 目录名推导
- Schema 定义: `references/graph-schema.md`

---

## 操作 1: 查询

### 输入
- `project`：项目名（如果用户未指定，从当前目录推断或 AskUserQuestion）
- `keywords`：关键词列表（文件名、API 路径、domain 名、类名）

### 流程
1. 确定 graph 文件路径：`~/.claude/knowledge-graph/<project>/graph.json`
2. 如果文件不存在 → 返回"该项目尚无知识图谱记录"
3. 在三个维度中模糊匹配：
   - `files`: 文件路径包含关键词
   - `apis`: API 路径包含关键词
   - `domains`: domain 名匹配关键词
4. 返回匹配到的所有 `touch_history` 和 `known_pain_points`

### 输出格式
```
知识图谱查询结果 [<project>]

文件: src/services/UserService.java
  - MIN-147 (2026-02-27): 修复 getProfile() NPE
  - MIN-152 (2026-03-01): 添加默认头像逻辑

API: GET /v1/users/{userId}
  - MIN-147 (2026-02-27): 修复 NPE

Domain: user
  已知痛点:
  - profile 字段可能为空，需判空
  相关 Issues: MIN-147, MIN-152
```

### 无结果时
返回："知识图谱中未找到相关记录。这是该区域的首次修改。"

---

## 操作 2: 写入

### 输入
- `project`：项目名
- 从 `task-state.json` 读取：
  - `meta.issue_id`
  - `meta.issue_type`
  - `implementation.files_modified`
  - `implementation.apis_touched`
  - `implementation.commit_messages`

### 流程
1. 确定 graph 文件路径：`~/.claude/knowledge-graph/<project>/graph.json`
2. 如果目录不存在 → `mkdir -p ~/.claude/knowledge-graph/<project>/`
3. 读取现有 graph.json（不存在则用空结构初始化）
4. 对每个 `files_modified`：
   - 如果文件已存在 → 追加 `touch_history` 记录
   - 如果文件不存在 → 创建条目，推断 `domain`
5. 对每个 `apis_touched`：
   - 如果 API 已存在 → 追加 `touch_history` 记录
   - 如果 API 不存在 → 创建条目，关联 controller_file / service_file（如能推断）
6. 推断 domain 并更新 `domains`：
   - 从文件路径中提取有意义的目录名作为 domain
   - 追加 `related_issues`
   - 追加 `key_files`（去重）
7. 如果在修复过程中发现 pain point → 追加到 `domains.known_pain_points`
8. 写回 graph.json

### domain 推断规则
从文件路径中提取有意义的模块/领域名：
- Java: 从包路径中取功能域目录（如 `.../user/service/...` → `user`）
- TypeScript/JS: 从目录结构取模块名（如 `src/modules/auth/...` → `auth`）
- 通用: 取 `src/` 后第一个有意义的目录名
- 如果无法推断 → domain = "unknown"

### 写入时机
- **仅在 push 后写入**（Phase 7）
- amend 期间不写入（代码还在变化）
- 写入的是最终状态

---

## 操作 3: 列出项目

### 流程
1. `ls ~/.claude/knowledge-graph/` 列出所有项目目录
2. 对每个项目读取 graph.json，统计 files/apis/domains 数量
3. 展示汇总

---

## 关键规则

1. **只读不改源文件** — 知识图谱只记录元数据，不修改任何源代码
2. **幂等写入** — 同一个 issue_id 对同一文件的多次写入不会重复（按 issue_id 去重）
3. **模糊匹配** — 查询时用包含匹配，不需要精确路径
4. **推断而非猜测** — domain 从路径推断，不确定时标记 "unknown"
5. **项目隔离** — 不同项目的知识图谱互不影响
