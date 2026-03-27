---
name: fof
description: 通用需求开发流程。给定需求描述，自动完成 worktree 创建、feature 分支、需求澄清、代码实现、编译、提交、推送、PR 创建。触发场景：执行 /fof 命令、用户说"开发一个新功能"、用户给出需求描述要求实现。
---
# fof

通用需求开发 skill，接收需求描述后自动完成完整的开发闭环。

## Phase 1: 需求接收与澄清

**目标**：理解需求并定位到模块/文件级别。

1. 读取用户提供的需求描述（来自 `/dev` 参数或对话上下文）。
2. 如果需求不够明确，通过 AskUserQuestion 循环澄清以下要点：
   - 涉及哪个服务？（kernel/os-main, kernel/os-ws, biz/os-user, kernel/base-datahub, frontend）
   - 改哪些模块/功能域？
   - 需求类型？（feature / bugfix / refactor / hotfix / chore）
3. 通过 Grep/Glob/Read 探索相关代码，定位要修改的文件。
4. 向用户确认修改范围（模块 + 关键文件列表），使用 AskUserQuestion 让用户确认或调整。
5. 本阶段输出：
   - 需求摘要（一句话）
   - 分支类型（feature / bugfix / refactor / hotfix）
   - 涉及模块路径列表
   - 关键文件列表

## Phase 2: 环境准备（Worktree + 分支）

**目标**：创建隔离的 worktree 工作环境。

monorepo 根目录：`/Users/songxuexian/IdeaProjects/mindverse02/secondme`

1. 进入 monorepo 根目录。
2. 拉取最新 master：
   ```bash
   cd /Users/songxuexian/IdeaProjects/mindverse02/secondme && git fetch origin master
   ```
3. 根据 Phase 1 的需求类型和描述，自动生成分支名（英文、kebab-case）：
   - 新功能：`feature/<area>-<short-desc>`
   - Bug 修复：`bugfix/<area>-<short-desc>`
   - 重构：`refactor/<area>-<short-desc>`
   - 热修复：`hotfix/<area>-<short-desc>`
   - 杂项：`chore/<area>-<short-desc>`
   - `<area>` 取模块名如 `kernel-os-main`、`biz-os-user`、`frontend`
   - `<short-desc>` 取 2-4 个英文单词概括需求
4. 创建 worktree：
   ```bash
   git worktree add .claude/worktrees/<branch-name> -b <branch-name> origin/master
   ```
5. 切换工作目录到 worktree：
   ```bash
   cd /Users/songxuexian/IdeaProjects/mindverse02/secondme/.claude/worktrees/<branch-name>
   ```
6. 验证 worktree 环境（关键目录存在）：
   ```bash
   ls kernel/os-main kernel/os-ws biz/os-user
   ```
7. 输出环境就绪信息：分支名、worktree 路径。

## Phase 3: 实现

**目标**：在 worktree 中完成代码修改。

1. 在 worktree 中按需求修改代码。
2. 严格遵循 CLAUDE.md 中的代码规范：
   - 分层架构：Controller -> Service -> DAO -> Mapper
   - 命名约定：`{Domain}Service`、`{Domain}ServiceImpl`、`{Domain}DAO`
   - MyBatis Plus 用法：LambdaQueryWrapper/LambdaUpdateWrapper
   - 所有 API 返回 `BaseResult<T>`
   - 使用 `@Slf4j` 而非手动创建 logger
   - 参数校验使用 `MorePreconditions.checkState`
3. 涉及 SDK 变更时严格遵循 SDK Version Management 规则：
   - RELEASE 版本（禁止 SNAPSHOT）
   - bump version
   - deploy SDK
   - 更新所有 consumer pom.xml
4. 实现过程中遇到不确定的设计决策，通过 AskUserQuestion 确认。

## Phase 4: 验证

**目标**：确保代码编译通过。

1. 在受影响的模块目录执行编译验证：
   ```bash
   cd <worktree-path>/<module-path> && mvn clean install -DskipTests -Dmaven.gitcommitid.skip=true
   ```
   - `-Dmaven.gitcommitid.skip=true` 是 worktree 环境必须参数。
   - 如果涉及多个模块，逐个编译或使用 `-pl` 指定模块。
2. 编译失败则分析错误、修复后重试，最多重试 3 次。
3. 编译通过后，展示变更摘要给用户确认：
   ```bash
   git diff --stat
   ```

## Phase 5: 提交与 PR

**目标**：提交代码、推送分支、生成 PR 链接。

1. 精确添加变更文件（不使用 `git add .`）：
   ```bash
   git add <file1> <file2> ...
   ```
2. 使用 Conventional Commits 格式提交：
   ```bash
   git commit -m "$(cat <<'EOF'
   <type>(<scope>): <summary>

   <详细描述（可选）>

   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```
   - type: feat / fix / refactor / chore / docs
   - scope: 模块名如 kernel/os-main、biz/os-user
3. 推送分支：
   ```bash
   git push -u origin <branch-name>
   ```
4. 生成 PR 创建链接（目标分支默认 `dev`）：
   ```bash
   OWNER_REPO=$(git remote get-url origin | grep -oE '[^/:]+/[^/]+\.git' | sed 's/\.git$//')
   BRANCH=$(git branch --show-current)
   echo "https://github.com/$OWNER_REPO/compare/dev...$BRANCH?expand=1"
   ```
5. 输出最终摘要：
   ```
   ========== 开发完成 ==========
   分支名：<branch-name>
   Worktree：<worktree-path>
   变更文件：
     - <file1>
     - <file2>
   提交：<commit-hash> <commit-message>

   请在浏览器中创建 PR:
   https://github.com/owner/repo/compare/dev...<branch>?expand=1
   ================================
   ```

## Phase 6: 自我进化（Retrospective）

**目标**：回顾本次执行过程，发现问题并自动改进 skill 定义。

每次 Phase 5 完成后（无论成功或失败），**必须**执行本阶段。

### 6.1 执行回顾

回顾整个 Phase 1-5 的执行过程，逐项检查：

| 检查维度 | 关注点 |
|----------|--------|
| 流程顺畅度 | 哪个 Phase 卡住了？是否有多余的步骤？是否缺少步骤？ |
| 编译问题 | 编译失败的原因是什么？是 skill 指令不完整还是代码问题？ |
| worktree 问题 | 创建/切换/清理是否顺利？路径是否正确？ |
| 分支命名 | 自动生成的分支名是否合理？用户是否需要修改？ |
| 澄清效率 | 需求澄清是否过多或过少？是否有可以跳过的问答？ |
| 用户干预 | 用户手动纠正了什么？这说明 skill 哪里需要改进？ |
| 耗时分布 | 哪个 Phase 耗时最长？是否可以优化？ |

### 6.2 判断是否需要进化

只在以下情况触发 skill 更新：
- 某个 Phase 执行失败或需要用户手动纠正
- 发现 skill 缺少关键步骤或指令不准确
- 发现重复出现的模式可以固化为规则
- 用户明确指出流程问题

**不更新**的情况：
- 纯业务代码 bug（不是流程问题）
- 一次性的网络/环境问题
- 用户主动变更需求（不算流程缺陷）

### 6.3 执行自我更新

如果判断需要进化：

1. **读取当前 SKILL.md**：
   ```
   Read ~/.claude/skills/fof/SKILL.md
   ```

2. **用 Edit 工具精确修改** SKILL.md 中需要改进的部分：
   - 补充缺失的步骤或命令
   - 修正不准确的指令
   - 添加从本次执行中学到的约束或最佳实践
   - 优化流程顺序

3. **追加进化日志**到 `~/.claude/skills/fof/EVOLUTION.md`：
   ```markdown
   ## <日期> - <简短描述>
   - **触发原因**：<什么问题导致了这次进化>
   - **改动内容**：<修改了 SKILL.md 的哪些部分>
   - **预期效果**：<下次执行时应该如何改善>
   ```

4. **输出进化摘要**给用户：
   ```
   🔄 Skill 自我进化
   问题：<发现的问题>
   改进：<做了什么修改>
   ```

### 6.4 进化边界

- **只改自己**：只修改 `~/.claude/skills/fof/` 下的文件，不改其他 skill
- **不改核心结构**：不删除或重排 Phase 1-5 的基本框架，只在框架内补充/修正
- **保守原则**：单次进化最多修改 SKILL.md 的 3 处，避免大幅重写
- **可追溯**：每次修改都记录在 EVOLUTION.md 中，方便用户审查

## 关键约束

| 约束 | 说明 |
|------|------|
| Worktree 编译 | 必须加 `-Dmaven.gitcommitid.skip=true` |
| 分支命名 | 严格遵循 CLAUDE.md 命名规范（英文 kebab-case） |
| SDK 变更 | RELEASE 版本、bump version、deploy、更新 consumer |
| 提交格式 | Conventional Commits：`<type>(<scope>): <summary>` |
| PR 目标 | 默认 `dev` 分支 |
| 保护分支 | 永远不直接推送到 master / dev / release/* |
| 文件添加 | 精确 `git add <files>`，禁止 `git add .` 或 `git add -A` |
| monorepo 根目录 | `/Users/songxuexian/IdeaProjects/mindverse02/secondme` |
