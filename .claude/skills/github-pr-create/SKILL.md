---
name: github-pr-create
description: 生成 GitHub PR 创建链接，用户手动在浏览器中创建 PR。
---
# github-pr-create

### 核心功能
生成 GitHub PR 创建链接，输出给用户在浏览器中手动创建 PR。

### 操作步骤

**步骤 1: 推送分支**
```bash
git push -u origin <branch-name>
```

**步骤 2: 生成 PR 创建链接**
```bash
# 获取仓库信息
OWNER_REPO=$(git remote get-url origin | grep -oE '[^/:]+/[^/]+\.git' | sed 's/\.git$//')

# 获取当前分支
BRANCH=$(git branch --show-current)

# 生成链接（目标分支默认 dev）
echo "https://github.com/$OWNER_REPO/compare/dev...$BRANCH?expand=1"
```

**步骤 3: 输出链接**
格式：
```
✅ 分支已推送: <branch-name>
📝 请在浏览器中创建 PR:
https://github.com/owner/repo/compare/dev...branch?expand=1
```

### PR 标题规范
**格式**: `<type>(<scope>): <description>`

类型：
- `fix`: 彻底修复
- `fix(<module>): mitigate ...`: 缓解性修复
- `feat`: 新功能
- `docs`: 文档
- `refactor`: 重构

### PR Body 必填项（修复类）
```markdown
## Summary
- 改动点1
- 改动点2

## Root Cause
文件路径:行号 + 触发条件

## Fix Type
- [x] Fully resolved / Mitigated

## Trigger Condition
触发场景描述

## Risk & Rollback
风险 + 回滚方案

## Test plan
- [ ] 测试项1
- [ ] 测试项2

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

### 链接格式说明
- `https://github.com/owner/repo/compare/dev...branch?expand=1`
  - `dev`: 目标分支（可改为 master）
  - `branch`: 源分支
  - `?expand=1`: 自动展开 PR 创建表单
