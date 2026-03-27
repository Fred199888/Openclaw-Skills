# Amend vs New Commit 决策规则

## 核心原则

在 linear-dev-fred 流程中，**默认使用 amend**，保持单一干净提交。

## 决策矩阵

| 场景 | 操作 | 原因 |
|------|------|------|
| 首次提交 | `git commit -m "..."` | 创建初始提交 |
| 用户说"改一下"/"调整" | `git commit --amend --no-edit` | 保持单一提交 |
| 用户说"再加一个 commit" | `git commit -m "..."` | 用户明确要求新提交 |
| 用户说"push" | `git push -u origin <branch>` | 推送到远程 |
| push 后用户说"改一下" | `git commit --amend --no-edit` + 告知需要 force push | 提醒用户 push 后 amend 需要 force push，而 force push 是禁止的 |

## push 后修改的处理

**push 后禁止 amend + force push。** 如果用户 push 后还要改：

1. 告知用户："已经 push 过了，amend 后需要 force push，但 force push 是禁止的。"
2. 建议用户：创建新的 commit 来修改。
3. 如果用户坚持要 amend + force push → 拒绝执行，解释风险。

## amend 流程

```
1. 修改代码
2. git add <specific files>
3. git commit --amend --no-edit
4. 更新 task-state.json（新 commit hash）
5. Linear 评论更新（最新提交状态）
```

## commit message 格式

```
<type>(<scope>): <description>

<optional body>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

- type: fix | feat | refactor | docs | test | chore
- scope: 模块路径（如 `kernel/os-main`）
- description: 简短描述，不超过 50 字符
- body: 可选，详细说明修改内容和原因
