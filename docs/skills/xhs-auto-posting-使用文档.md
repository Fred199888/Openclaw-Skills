# xhs-auto-posting - 使用文档

来源：.openclaw/skills/xhs-auto-posting/SKILL.md

---
name: xhs-auto-posting
description: 自动化小红书 MBTI 图文生产与发布流程：读取选题/文案，按 MBTI 类型绑定参考人物图（SVG→PNG），用火山方舟图片生成 API 出图，生成标题正文并发布到小红书创作平台。用于日常定时发帖、草稿生成、失败告警与人工兜底。
---

# xhs-auto-posting

按以下顺序执行。

## 1. 读取配置
- 先加载 `/Users/songxuexian/Desktop/workspace/xhs/.env`（所有路径与规则以 .env 为准）。
- 再读取 `references/config.md`。
- 必要环境变量：`ARK_API_KEY`。
- 默认模型：`doubao-seedream-5-0-260128`。

## 2. 准备素材
- 将 `xhs/img/*.svg` 转换为 `xhs/assets/mbti_png/*.png`。
- 读取 `xhs/assets/mbti_manifest.json`，确保 16 类型齐全。
- 文案中出现的 MBTI 类型，必须绑定 manifest 中同类型图片；缺失则终止该任务。

## 3. 生成 Prompt
- 按 `references/prompt-framework.md` 生成结构化 prompt。
- 双人格对抗/对比时，额外读取 `references/scene-framework.md`，按变量动态填充场景、动作、眼神、冲突，不可写死模板。
- 规则：人物身份保持一致；背景、动作、镜头、光影细节完整；可调皮恶搞但需合规。
- 产出粒度规则：
  - 输入 1 个 MBTI：走“单人格分析”模式（1 图 1 文）。
  - 输入 2 个 MBTI：走“对抗/对比”模式（2 人格同画面）。必须上传并绑定两张对应参考图，按 A/B 人格一一对应传给模型。
  - 禁止把 16 人格混成一条内容。

## 4. 调 Ark 生成图片
- 使用图生图（`image` 传 base64）。
- 推荐参数：
  - `size: 1728x2304`
  - `output_format: png`
  - `response_format: url`
  - `watermark: false`
  - `optimize_prompt_options.mode: standard`
- 若命中安全拦截：自动降级为“轻松幽默、无攻击性”版 prompt 重试 1 次。

## 5. 发布小红书
- 使用已登录浏览器会话进入 `https://creator.xiaohongshu.com/publish/publish`。
- 上传封面图，填标题与正文。
- 上传恢复策略（必须执行）：
  1) 先尝试标准 `upload`。
  2) 若注入后前端未接收（文件数=0或未进入编辑页），刷新到干净发布页并重试一次。
  3) 若仍失败，自动切换“文字配图”兜底路径，继续完成文案、话题与草稿/发布流程。
- 标题硬规则：必须 `<= 20` 个中文字符；超出时自动压缩重写后再填入。
- 正文填充时不要手动输入 `#话题` 文本，避免变成纯文本。
- 话题必须通过平台“话题”入口添加：点击“话题”按钮后，逐个选择推荐/联想话题。
- 话题选择规则：优先点击推荐项中的前 5 个左右（目标 4~6 个，以相关度为准，去重；平台上限按 10 处理）。
- 至少包含：`MBTI`、`{MBTI_TYPE}`（双人格时包含两个 MBTI）。
- 话题位置规则：话题必须追加在正文末尾单独一行，不允许插入到句子中间。
- 结尾互动规则：不要固定使用同一句（如“你站哪一边”）。应根据场景随机生成互动收尾（投票/二选一/经历提问/观点挑战）。
- 发布前校验：
  - 正文区应出现可识别的话题标记（如带“[话题]”标识或可点击话题样式）；若仅是普通 `#` 文本则视为失败并重做话题步骤。
  - 若检测到“句子被话题打断”（如“你站哪 #xxx 边”）则自动清理并把话题重新追加到文末。
- 默认发布；可切换成“仅存草稿”。

## 6. 告警与人工介入
- 读取 `xhs/xhs_alert_policy.yaml`。
- 登录失效、风控、连续失败归为 P1，立即飞书通知。
- 失败时保留产物与日志，不做不可恢复删除。

## 7. 脚本入口（必须优先使用）
- 规则校验：
  - `python3 scripts/validate_rules.py`
- 生成工作流（单/双人格自动识别）：
  - `python3 scripts/run_workflow.py --personas "ENTJ" --mode draft`
  - `python3 scripts/run_workflow.py --personas "ENTJ vs ISTP" --mode draft`
  - `python3 scripts/run_workflow.py --personas "ENTJ" --mode publish`

## 8. 输出产物
- 图片：`xhs/output/images/post*/`
- Prompt：`xhs/output/prompts_*.json`
- 文案：`xhs/output/copy_*.md`
- 运行日志：`xhs/output/logs/*.log`
