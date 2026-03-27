# linear-dev-fred — Linear 任务驱动开发

## 描述
从 Linear 读取任务，在 worktree 中开发，commit 不 push，积累知识图谱。支持任意项目。

## 触发场景
- 用户说 `/linear-dev-fred MIN-xxx`
- 用户说"做 MIN-xxx"或"开始 MIN-xxx"

## 参数
- `issue_id`：Linear issue identifier（如 `MIN-147`）
- `phase`（可选）：从指定 Phase 开始执行（默认自动判断）

## 前置条件
- Linear MCP 工具可用（mcp__linear__*）
- 当前目录或 task-state.json 中有目标项目的 git repo 路径

## 持久化
- task-state: `~/.claude/linear-tasks/<issue-id>/task-state.json`
- knowledge-graph: `~/.claude/knowledge-graph/<project>/graph.json`（按项目隔离）

---

## 流程：7 Phase

### Phase 0: 断点续传

1. 读取 `~/.claude/linear-tasks/<issue-id>/task-state.json`
2. **存在** → 恢复上下文：
   - 读取 git 状态（repo 路径、分支、worktree 路径、commit hash）
   - `mcp__linear__list_comments(issueId)` 读取之前的阶段评论，恢复实现上下文
   - 检查 worktree 是否存在（`ls <worktree_path>`）
   - 告知用户当前状态，继续上次中断的 Phase
3. **不存在** → 进入 Phase 1

### Phase 1: 任务读取与需求澄清

1. `mcp__linear__get_issue(issueId)` 读取任务详情
2. 根据 title / labels / description 判断任务类型：
   - 有 `bug` 标签或 title 含"修复/fix/NPE/异常/报错/error" → `bugfix`
   - 有 `feature` 标签或 title 含"新增/添加/支持/add/implement" → `feature`
   - 其他 → `refactor`
3. **确定项目**：
   - 如果当前目录是 git repo → 自动识别为目标项目
   - 否则 AskUserQuestion 让用户指定 repo 路径
   - 项目名（project slug）从 repo 目录名推导（如 `secondme`、`my-app`）
4. 查询 `knowledge-graph-fred`：
   - 从 title/description 提取关键词（文件名、API 路径、domain 名）
   - 在 `~/.claude/knowledge-graph/<project>/graph.json` 中模糊匹配
   - 有历史记录 → 展示给用户（"这个文件之前在 MIN-xxx 中被修改过，改了 xxx"）
5. AskUserQuestion 澄清：
   - 涉及哪个服务/模块？
   - 我的理解是否正确？
   - 有补充信息吗？（traceId、复现步骤等）
6. **不修改 Linear 状态**

### Phase 2: 环境准备

1. `cd <repo_path>`
2. `git fetch origin`，检测主分支名（master / main）
3. 确定分支名：`<type>/min-<number>-<area>-<short-desc>`
   - type: bugfix / feature / refactor
   - area: 从涉及的模块推断
   - short-desc: 2-3 个词描述（kebab-case）
   - 示例: `bugfix/min-147-homepage-cover-npe`
4. 创建 worktree：
   ```bash
   git worktree add .claude/worktrees/<branch> -b <branch> origin/<main-branch>
   ```
5. **写入 task-state.json（CP1）**：
   ```json
   {
     "meta": {
       "issue_id": "<issue-id>",
       "issue_title": "<title>",
       "issue_type": "<type>",
       "project": "<project-slug>",
       "repo_path": "<absolute repo path>",
       "started_at": "<ISO timestamp>"
     },
     "git": {
       "branch": "<branch>",
       "main_branch": "<master|main>",
       "worktree": "<repo_path>/.claude/worktrees/<branch>",
       "base_commit": "<hash>",
       "current_commit": null,
       "push_status": "pending",
       "pr_url": null
     },
     "implementation": {
       "files_modified": [],
       "apis_touched": [],
       "commit_messages": []
     },
     "session_log": [
       { "ts": "<ISO>", "action": "task_started", "note": "Phase 2 完成" }
     ]
   }
   ```
6. **Linear 评论（CP1）**：`mcp__linear__create_comment`
   ```
   [Phase 2] 环境就绪
   项目: <project>
   分支: <branch>
   Worktree: <worktree_path>
   Base commit: <hash>
   ```

### Phase 3: 实现

1. 先查 knowledge-graph-fred 获取相关文件历史
2. 在 worktree 中实现修改
3. 实现方式由任务内容决定：
   - 阅读相关代码 → 理解上下文 → 编写/修改代码
   - 参考 CLAUDE.md 或项目自身的编码规范
   - 如果项目有特定的 skill（如 `worker-fix-java`），可以调用其 diagnose 能力辅助分析

#### 实现完成后
- 更新 task-state.json 的 `implementation` 字段
- **Linear 评论（CP2）**：`mcp__linear__create_comment`
  ```
  [Phase 3] 实现完成
  修改文件:
  - <file1> (L<line>: <change summary>)
  - <file2> ...
  APIs 涉及: <method> <path>（如有）
  根因: <root cause>（bugfix 时填写）
  修复方案: <fix description>
  ```

### Phase 4: 验证

1. **自动检测构建方式**（在 worktree 中）：
   - 有 `pom.xml` → `mvn clean install -DskipTests`
   - 有 `build.gradle` / `build.gradle.kts` → `./gradlew build -x test`
   - 有 `package.json` → `npm run build` 或 `yarn build`
   - 有 `Cargo.toml` → `cargo build`
   - 有 `go.mod` → `go build ./...`
   - 其他 → AskUserQuestion 询问构建命令
2. `git diff --stat` 展示变更概要
3. AskUserQuestion 确认：
   - 变更是否符合预期？
   - 需要修改吗？
   - 如果需要修改 → 回到 Phase 3

### Phase 5: 提交（支持 amend 循环）

#### 首次 commit
1. `git add <specific files>`（只 add 修改的文件，不用 `git add .`）
2. commit message 格式：`<type>(<scope>): <description>`
   - type: fix / feat / refactor
   - scope: 模块/目录路径
   - description: 简短描述
3. `git commit`（使用 HEREDOC 传递 message，末尾含 Co-Authored-By）
4. 更新 task-state.json（CP3）：
   - `git.current_commit` = 新 commit hash
   - `implementation.commit_messages` 追加
   - `session_log` 追加 `committed` 记录
5. **告知用户**："已提交未推送。说'改一下'会 amend，说'push'才推送"

#### amend 模式（用户说"改一下"/"调整一下"）
1. 修改代码
2. `git add <files>`
3. `git commit --amend --no-edit`
4. 更新 task-state.json：
   - `git.current_commit` = 新 hash
   - `session_log` 追加 `amended` 记录

#### Linear 评论（CP3）
每次 commit 或 amend 后，`mcp__linear__create_comment`：
```
[Phase 5] 当前提交状态
Commit: <hash>
Message: <commit message>
修改文件:
- <file> (+N -M)
构建: 通过
Push: 待推送
```

### Phase 6: 推送（用户明确触发）

**仅当用户明确说"push"/"推送"/"推"时执行。**

1. `git push -u origin <branch>`（**禁止 --force**）
2. 生成 PR 比较链接（目标分支由用户指定，默认 AskUserQuestion 询问）
3. 更新 task-state.json：
   - `git.push_status` = "pushed"
   - `git.pr_url` = PR 链接
4. **Linear 评论（最终版）**：`mcp__linear__create_comment`
   ```
   [完成] 开发完成
   项目: <project>
   分支: <branch>
   提交: <hash> <commit message>
   修改文件:
   - <full file path>
   APIs: <method> <path>（如有）
   根因: <root cause>（bugfix 时）
   修复: <fix description>
   PR: <pr url>
   ```
5. 自动进入 Phase 7

### Phase 7: 知识图谱更新

push 完成后自动执行（不需要用户触发）。

1. 读取 task-state.json 的 `meta.project` 和 `implementation` 字段
2. 调用 knowledge-graph-fred 的写入操作（目标：`~/.claude/knowledge-graph/<project>/graph.json`）：
   - 对每个 `files_modified` 文件，追加 touch_history 记录
   - 对每个 `apis_touched` API，追加 touch_history 记录
   - 更新 domains 的 related_issues 和 key_files
3. 如果发现 known_pain_points，追加到 domains

---

## 关键规则

### 禁止操作
- **禁止 git push --force**（任何形式）
- **禁止 git reset --hard**
- **禁止自动修改 Linear 任务状态**（只写评论，不改 status）
- **禁止 git add . 或 git add -A**（只 add 具体文件）

### commit 策略
- 默认 commit 后不 push，等用户指示
- 用户说"改一下" → amend
- 用户说"push" → 推送
- 详见 `references/amend-strategy.md`

### Linear 评论策略
- Phase 2 完成：写环境信息评论
- Phase 3 完成：写实现摘要评论
- Phase 5 每次 commit/amend：写提交状态评论
- Phase 6 push：写最终完成评论（最完整）
- 评论是**递进累积**的，最后一条最完整
- 评论也是**上下文恢复源**：Phase 0 通过读评论恢复实现上下文

### worktree 管理
- worktree 路径：`<repo>/.claude/worktrees/<branch>`
- 所有 git 操作在 worktree 中执行（`cd <worktree_path>` 或 `-C <worktree_path>`）
- push 后不自动删除 worktree（用户可能还要 amend）

### 多项目隔离
- 每个项目的知识图谱独立：`~/.claude/knowledge-graph/<project>/graph.json`
- task-state.json 中记录 `meta.project` 和 `meta.repo_path`
- 同一个 Linear issue 只关联一个项目
