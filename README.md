# Openclaw Skills

Openclaw 团队的 Claude Code Skills 集合。包含 KOL 运营、内容创作、线上修复、微信工具等多个自动化技能。

## 快速迁移到新机器

```bash
# 1. 克隆仓库
git clone git@github.com:Fred199888/Openclaw-Skills.git
cd Openclaw-Skills

# 2. 复制 skills 到 Claude Code 目录
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
| `xhs-ba` | 小红书博主分析 + 夸赞话术生成器 | 无 |
| `xhs-mbti-trending` | 抓取小红书近一周 MBTI 热帖 Top 50 | 无 |

### 内容创作（文章转视频）

| 技能 | 用途 | 需要 .env |
|------|------|-----------|
| `article-to-video` | 全流程编排：文章 → 解说词 → 语音 → 幻灯片 → 视频 | 系统环境变量 |
| `article-fetch` | 抓取网页文章完整内容和关键图片 | 无 |
| `narration-gen` | 将文章生成中文视频解说词脚本 | 无 |
| `tts-gen` | 火山引擎 TTS 生成分段 MP3 音频 | 系统环境变量 |
| `video-assemble` | PPT 幻灯片 + 音频合成 MP4 视频 | 无 |

### 线上修复（SecondMe Monorepo）

| 技能 | 用途 | 需要 .env |
|------|------|-----------|
| `bug-fix` | 硅谷 prod 告警批量自动修复工作流 | 独立 .env 体系 |
| `worker-fix-java` | 单条 issue 闭环修复（CLS → 诊断 → 修复 → PR） | 无 |
| `cls-log-query` | 腾讯云 CLS 日志查询 | 无 |
| `env-check-multi-repo` | SecondMe monorepo 环境检查 | 无 |
| `fof` | 通用需求开发流程（worktree + 分支 + 实现 + PR） | 无 |
| `github-pr-create` | 生成 GitHub PR 创建链接 | 无 |

### 微信工具

| 技能 | 用途 | 需要 .env |
|------|------|-----------|
| `vx-secret` | macOS 微信聊天记录提取与查询（进程内存密钥提取） | 运行时生成 keys.json |
| `vx-digest` | 微信群消息消费 + 飞书报表 | 本地 |

### 通用工具

| 技能 | 用途 |
|------|------|
| `metaskill` | 创建 AI agent 团队、个体 agent 或自定义 skill |
| `metabot` | MetaBot API 协作：委派任务、调度、管理 |
| `metamemory` | 跨会话共享记忆读写 |
| `skill-creator` | 创建新 skill 的引导工具 |
| `knowledge-graph-fred` | 功能知识图谱 |
| `linear-dev-fred` | Linear 任务驱动开发 |

## 环境变量配置

### 全局认证：`~/.claude/skills/xhs-global.env`

这是最重要的配置文件，所有 KOL 运营类 skill 共享。

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

### 文章转视频：系统环境变量

TTS 功能需要火山引擎凭据，建议加到 shell profile 中：

```bash
# ~/.zshrc 或 ~/.bashrc
export VOLCANO_APPID="你的火山引擎 App ID"   # 火山引擎控制台 → 语音技术 → 应用管理
export VOLCANO_TOKEN="你的火山引擎 Token"     # 同上，获取 Access Token
```

### 线上修复：独立配置体系

`bug-fix` 和 `worker-fix-java` 使用独立的 `.env` 体系（位于 `~/Desktop/workspace/claude-code-deploy/scripts/.env`），包含 monorepo 路径、CLS Region、飞书群/表 ID 等。详见 `bug-fix/SKILL.md` 中的说明。

## 系统依赖

```bash
# Python 依赖（内容创作类 skill）
pip install requests pydub Pillow

# 系统工具
brew install ffmpeg    # 视频合成

# 微信工具（仅 macOS）
# vx-secret 需要 WeChat 4.x 运行中
```

## 目录结构

```
.claude/skills/
├── xhs-global.env.example     # 全局认证模板（复制为 xhs-global.env 后填值）
├── article-fetch/              # 网页文章抓取
├── article-to-video/           # 文章转视频编排器
├── bug-fix/                    # 线上告警批量修复
├── cls-log-query/              # CLS 日志查询
├── ...
└── xingtu-kol-crawl-all/       # 星图 KOL 抓取
```

每个 skill 目录包含：
- `SKILL.md` — 技能定义（frontmatter + 执行逻辑）
- `scripts/` — Python 脚本（如有）
- `.env.example` — 环境变量模板（如需配置）
