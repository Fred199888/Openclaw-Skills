# Openclaw-Skills 打包说明

这个目录可用于“拖拽迁移”到另一台电脑。

## 包含内容
- `.openclaw/skills/`：你的自定义技能
- `.openclaw/config.json`、`.openclaw/openclaw.json`：当前 OpenClaw 配置
- `.openclaw/cron/`：当前定时任务数据
- `docs/skills/*`：每个 skill 的使用文档
- `docs/定时任务教学文档.md`

## 使用方式
将本目录中的 `.openclaw` 拖拽/复制到目标机器用户主目录（`~/`）下，与目标机器现有 `.openclaw` 合并。

建议先备份目标机器原 `.openclaw`。
