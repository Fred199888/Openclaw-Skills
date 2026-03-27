---
name: env-check-multi-repo
description: 检查 SecondMe monorepo 的状态、远端、分支与提交，验证四个服务子目录存在，必要时 stash。
---
# env-check-multi-repo

## Instructions
1. 输出中文；进入 monorepo 根目录：`$MONOREPO_DIR`（默认 `/Users/songxuexian/IdeaProjects/mindverse02/secondme`）。
2. 输出 pwd 和 ls，确认这是 git 仓库根目录（存在 .git 目录）。
3. 验证四个服务子目录存在（在 repo 根目录执行）：
   - `ls kernel/os-main`
   - `ls kernel/os-ws`
   - `ls kernel/base-datahub`
   - `ls biz/os-user`
4. 在 repo 根目录执行一次 git 检查（不进入子目录）：
   - `git fetch origin master`（拉取远端最新，不切换分支）
   - `git remote -v`（确认远端地址）
   - `git branch --show-current`（当前分支）
   - `git status`（工作区状态）
   - `git log --oneline -1`（最近一次提交 hash + message）
5. 若工作区不干净（git status 有未提交变更），在 repo 根目录执行一次 `git stash`，并记录 stash hash 与原因。
   - 所有 stash 操作只在 repo 根目录执行一次，不得分子目录 stash。
6. 任何失败按失败记录模板输出并继续检查下一步骤。

## ⛔ 禁止操作
- **不要执行 `git checkout` / `git switch`，不要改变当前分支**
- 本 Skill 是只读检查，仅 fetch + 读取状态，绝不切换分支

## 服务路径映射（供后续 worker 参考）

| K8s 服务名 | monorepo 内路径 |
|-----------|----------------|
| os-main-inner-prod | kernel/os-main/ |
| os-main-out-prod | kernel/os-main/ |
| os-main-runner-prod | kernel/os-main/ |
| os-ws-api-prodk8sNew | kernel/os-ws/ |
| os-ws-websocket-prodk8sNew | kernel/os-ws/ |
| os-ws-runner-prodk8sNew | kernel/os-ws/ |
| base-datahub-prod | kernel/base-datahub/ |
| os-user-prodk8s | biz/os-user/ |

## 输出格式

```
═══════════ 环境检查 ═══════════
仓库根目录：/Users/songxuexian/IdeaProjects/mindverse02/secondme
Git 状态：✅ 干净 / ⚠️ 有未提交变更（已 stash，hash: xxx）

服务目录检查：
  ✅ kernel/os-main
  ✅ kernel/os-ws
  ✅ kernel/base-datahub
  ✅ biz/os-user

Git 信息：
  远端：<remote-url>
  当前分支：<branch>
  最近提交：<hash> <message>
═══════════════════════════════
```
