# Openclaw Skills

Openclaw 团队的 Claude Code Skills 集合 — KOL 运营（小红书 + 巨量星图）、微信工具。

## 快速迁移到新机器

```bash
# 1. 克隆仓库
git clone git@github.com:Fred199888/Openclaw-Skills.git
cd Openclaw-Skills

# 2. 复制 skills 到 Claude Code 目录
mkdir -p ~/.claude/skills
cp -r .claude/skills/* ~/.claude/skills/

# 3. 复制全局环境变量模板并填写
cp ~/.claude/skills/xhs-global.env.example ~/.claude/skills/xhs-global.env
# 编辑 xhs-global.env，填入实际认证参数（见下方"环境变量"章节）

# 4. 各 skill 的本地 .env（有 .env.example 的目录都需要）
cd ~/.claude/skills
for d in */; do
  [ -f "$d/.env.example" ] && [ ! -f "$d/.env" ] && cp "$d/.env.example" "$d/.env"
done
# 然后逐个编辑 .env，填入飞书表 ID 等配置
```

## 技能一览

### KOL 运营（小红书 + 巨量星图）

| 技能 | 用途 | 需要 .env |
|------|------|-----------|
| `xhs-kol-crawl-all` | 关键词全量抓取小红书蒲公英 KOL，同步到飞书多维表 | 全局 + 本地 |
| `xhs-invite-batch` | 批量发送小红书蒲公英 KOL 邀约，回写进度 | 全局 + 本地 |
| `xingtu-kol-crawl-all` | 关键词全量抓取巨量星图 KOL，同步到飞书多维表 | 全局 + 本地 |
| `xingtu-invite-batch` | 批量发送巨量星图 KOL 邀约，回写进度 | 全局 + 本地 |
| `kol-to-video-sync` | 将 KOL 总表有效记录同步到视频渠道建设表 | 本地 |
| `kol-progress-to-video-sync` | 将活动 BD 表进度沉淀到视频渠道建设表 | 本地 |

### 微信工具

| 技能 | 用途 | 需要 .env |
|------|------|-----------|
| `vx-secret` | macOS 微信聊天记录提取与查询（进程内存密钥提取） | 运行时生成 keys.json |
| `vx-digest` | 微信群消息消费 + 飞书报表 | 本地 |

## 环境变量配置

### 全局认证：`~/.claude/skills/xhs-global.env`

所有 KOL 运营类 skill 共享的认证文件。

```bash
cp ~/.claude/skills/xhs-global.env.example ~/.claude/skills/xhs-global.env
```

| 变量 | 获取方式 | 用于 |
|------|----------|------|
| `XHS_COOKIE` | 登录 pgy.xiaohongshu.com → F12 → Network → 复制请求 Cookie | 小红书蒲公英 API 认证 |
| `XHS_X_S` | 同上，复制 `x-s` 请求头 | 小红书 API 签名 |
| `XHS_X_S_COMMON` | 同上，复制 `x-s-common` 请求头 | 小红书 API 签名 |
| `XHS_X_T` | 同上，复制 `x-t` 请求头 | 小红书 API 时间戳 |
| `XHS_BRAND_USER_ID` | Cookie 中 `x-user-id-pgy.xiaohongshu.com` 的值 | 品牌用户标识 |
| `XHS_TRACK_ID` | 同上（可选） | 追踪标识 |
| `XINGTU_COOKIE` | 登录 star.toutiao.com → F12 → Network → 复制请求 Cookie | 巨量星图 API 认证 |
| `XINGTU_CSRF_TOKEN` | 同上，复制 `x-secsdk-csrf-token` 请求头 | 巨量星图 CSRF 验证 |
| `FEISHU_APP_ID` | 飞书开放平台 → 应用管理 → App ID | 飞书 API 认证 |
| `FEISHU_APP_SECRET` | 同上 → App Secret | 飞书 API 认证 |

> **注意**：XHS 和 Xingtu 的 Cookie/Token 会过期（通常 1-7 天），需要定期更新。

### 各 Skill 本地 `.env`

以下 skill 有自己的 `.env` 配置（已提供 `.env.example` 模板）：

| Skill | 关键变量 | 说明 |
|-------|----------|------|
| `xhs-kol-crawl-all` | `XHS_KOL_APP_TOKEN`, `XHS_KOL_TABLE_ID` | 飞书多维表格 ID（从表 URL 获取） |
| `xhs-invite-batch` | `XHS_KOL_APP_TOKEN`, `XHS_COOPERATE_BRAND_ID` | 飞书表 + 蒲公英品牌 ID |
| `xingtu-kol-crawl-all` | `XINGTU_KOL_APP_TOKEN`, `XINGTU_KOL_TABLE_ID` | 飞书多维表格 ID |
| `xingtu-invite-batch` | 邀约参数（产品名、预算、类目等） | 业务配置，无需认证 |
| `kol-to-video-sync` | `XHS_KOL_APP_TOKEN`, `VIDEO_APP_TOKEN` | 两张飞书表的 ID |
| `kol-progress-to-video-sync` | `VIDEO_APP_TOKEN`, `SOURCE_TABLE_*` | 视频表 + 来源表 ID |
| `vx-digest` | `VX_BITABLE_APP_TOKEN`, `VX_GROUP_NAMES` | 飞书表 + 要消费的群名 |

> **飞书多维表格 ID 获取方式**：打开飞书多维表格 URL，格式为 `https://xxx.feishu.cn/base/{app_token}?table={table_id}`

## 系统依赖

```bash
pip install requests

# 微信工具（仅 macOS，需要 WeChat 4.x 运行中）
```

## 目录结构

```
.claude/skills/
├── xhs-global.env.example          # 全局认证模板
├── xhs-kol-crawl-all/              # 小红书 KOL 抓取
├── xhs-invite-batch/               # 小红书 KOL 邀约
├── xingtu-kol-crawl-all/           # 星图 KOL 抓取
├── xingtu-invite-batch/            # 星图 KOL 邀约
├── kol-to-video-sync/              # KOL → 视频表同步
├── kol-progress-to-video-sync/     # 活动进度 → 视频表同步
├── vx-secret/                      # 微信聊天记录提取
└── vx-digest/                      # 微信群消息消费
```

每个 skill 目录包含：
- `SKILL.md` — 技能定义（frontmatter + 执行逻辑）
- `scripts/` — Python 脚本（如有）
- `.env.example` — 环境变量模板（如需配置）
