---
name: worker-fix-java
description: 单问题闭环修复（含自诊断），含跨模块根因追溯、tid 追踪、编译、提交、推送、PR、飞书写入。在 SecondMe monorepo 内操作。支持分阶段执行（phase 参数），阶段间通过 JSON 文件传递数据，防止长上下文幻觉。
---
# worker-fix-java

## 分阶段执行

### 2 阶段分离

```
Phase A（诊断，只读）→ diagnosis.json → Dispatcher 验证 → Phase B（修复+编译+提交+推送）→ fix-result.json
```

- Phase A: 只读操作（Grep/Read 代码 + 制定修复计划），**不需要 worktree 隔离**
- Phase B: 修改代码 + 编译 + commit + push，**需要 worktree 隔离**
- Dispatcher 在 Phase A → B 之间做幻构检测（验证文件存在性、代码行匹配）

### phase 参数

| phase | 包含步骤 | 输入 | 输出 |
|-------|---------|------|------|
| `diagnose` | Step 1-4 | 告警参数 + CLS 摘要 | `{output_dir}/diagnosis.json` |
| `fix` | Step 5-8 | diagnosis.json | `{output_dir}/fix-result.json` |
| `full`（默认，向后兼容） | Step 1-8 | 告警参数 | Worker 回执 |

### output_dir 参数

每个 phase 的输出路径由 orchestrator 通过 `output_dir` 参数指定。
- 如果未指定，默认为 `/tmp/worker/{issue_id}/`
- orchestrator 通常传入 `/tmp/bugfix/{round}/fix/{issue_id}/`

### diagnosis.json 格式

**可修复示例：**
```json
{
  "issue_id": "I001",
  "service": "os-main-inner-api",
  "service_path": "kernel/os-main/",
  "root_cause": {
    "file": "kernel/os-main/os-main-inner-api/src/.../MindController.java",
    "method": "getPublicProfile",
    "line": 548,
    "description": "simplePublicHomepage 可能为 null，访问 .getCover() 导致 NPE"
  },
  "fix_plan": {
    "type": "根本修复",
    "changes": [
      {
        "file": "kernel/os-main/os-main-inner-api/src/.../MindController.java",
        "line_range": "548",
        "old_code": "String ogImage = StrUtil.isNotBlank(simplePublicHomepage.getCover()) ? ...",
        "new_code": "String ogImage = (simplePublicHomepage != null && StrUtil.isNotBlank(simplePublicHomepage.getCover())) ? ...",
        "reason": "添加 null check 防止 NPE"
      }
    ],
    "compile_cmd": "mvn clean install -DskipTests ..."
  },
  "search_evidence": [
    {"command": "Grep(pattern='unexpected.error', path='kernel/os-main/', type='java')", "result": "找到 3 处: GlobalExceptionHandler.java:45, MindController.java:548, ..."},
    {"command": "Read('kernel/os-main/.../MindController.java', offset=540, limit=20)", "result": "确认 line 548 访问 simplePublicHomepage.getCover()"}
  ],
  "upstream_analysis": {
    "root_in_monorepo": true,
    "upstream_service": null,
    "tracking_actions": []
  }
}
```

**不可修复示例（合法格式）：**
```json
{
  "issue_id": "I002",
  "service": "os-main-inner-api",
  "service_path": "kernel/os-main/",
  "root_cause": {
    "file": "kernel/os-main/os-main-component/src/.../EmbeddingsServiceImpl.java",
    "method": "callEmbeddingsV3",
    "line": 123,
    "description": "调用外部 EmbeddingsV3 API 返回错误，非 monorepo 代码问题"
  },
  "fix_plan": {
    "type": "无法修复",
    "changes": [],
    "reason": "根因在外部 EmbeddingsV3 API 服务端，monorepo 内仅为调用方，无法修复"
  },
  "search_evidence": [
    {"command": "Grep(pattern='embeddingsV3', path='kernel/os-main/', type='java')", "result": "EmbeddingsServiceImpl.java:123 调用外部 API"},
    {"command": "Read('kernel/os-main/.../EmbeddingsServiceImpl.java', offset=110, limit=30)", "result": "确认为 HTTP 调用外部服务"}
  ],
  "upstream_analysis": {
    "root_in_monorepo": false,
    "upstream_service": "EmbeddingsV3 API",
    "tracking_actions": ["联系 EmbeddingsV3 服务维护方排查"]
  }
}
```

**格式硬性要求（违反任何一条 → diagnosis 被拒绝）：**
- `root_cause` **必须是对象** `{file, method, line, description}`，**永远不能是字符串**
- `fix_plan` **必须是对象**，**永远不能是 null**（不可修复时 `{"type": "无法修复", "changes": [], "reason": "..."}`)
- `search_evidence` **数组必须存在**（无堆栈时必填），列出所有 Grep/Read 命令及结果
- **禁止自创规范外字段**（如 category、fixable、is_external、skip_reason 等）

### fix-result.json 格式

```json
{
  "issue_id": "I001",
  "fix_status": "success",
  "precise_fingerprint": "os-main-inner-api_mind-public-profile_unexpected.error_MindController.java:548",
  "files_modified": ["kernel/os-main/os-main-inner-api/src/.../MindController.java"],
  "compile_status": "BUILD SUCCESS",
  "branch": "fix/cc/20260227/unexpected-error",
  "commit": "d63f64a9",
  "push_status": "success",
  "reply_summary": {
    "fix_type": "等待合并",
    "root_cause_brief": "simplePublicHomepage null 时访问 .getCover() 导致 NPE",
    "fix_description_brief": "添加 null check"
  },
  "lark_reply_content": "服务: os-main-inner-api  接口: /rest/os/mind/public/profile\n\n问题分析:\nsimplePublicHomepage 查询返回 null 时，MindController.java:548\n直接调用 .getCover() 导致 NPE。该接口在用户未设置主页封面时必现。\n\n修复方案:\n在 getCover() 调用前添加 null 检查，simplePublicHomepage 为空时使用默认封面。\n修改文件: MindController.java"
}
```

**bitable 写入时额外字段**（所有 fix_status 均适用）：
- `error_type`: 异常类名短名（如 `NullPointerException`），从 `raw_error_message` 提取
- `error_location`: CLS 提取的错误位置（如 `VideoService.java:123`），来自 orchestrator 参数
- `involved_topics`: CLS 查询命中的日志库名称列表（逗号分隔），来自 orchestrator 参数
- `stack_trace`: `stack_trace_top3` 截取前 500 字符

**fix_status=diagnosed 时的必填字段**（已找到根因但无法自动提交时）：

```json
{
  "fix_status": "diagnosed",
  "diagnosis_detail": {
    "root_cause_file": "MindController.java",
    "root_cause_line": 700,
    "root_cause_code": "userSettings.getSelfIntroduction()",
    "why_npe": "getUserSettings() 在用户未设置时返回 null，未做 null check",
    "trace_chain": [
      "CLS 日志: NPE at MindController.java:700",
      "Read MindController.java:695-710: userSettings = getUserSettings(userId)",
      "Read MindController.java:700: userSettings.getSelfIntroduction() 无 null guard",
      "Read UserService.java: getUserSettings 在无记录时返回 null"
    ]
  },
  "suggested_fix": {
    "description": "在第 700 行前增加 null check",
    "code_diff": "if (userSettings == null) { return ResponseResult.fail(\"settings not found\"); }\nString intro = userSettings.getSelfIntroduction();"
  },
  "why_not_auto_fixed": "worktree git remote 未配置，无法自动推送",
  "manual_steps": [
    "1. 切换到 master 分支",
    "2. 在 MindController.java 第 700 行前增加上述 null check",
    "3. 编译验证：mvn compile -pl kernel/os-main",
    "4. 提交 PR"
  ],
  "reply_summary": {
    "fix_type": "已诊断待人工修复",
    "root_cause_brief": "MindController.java:700 userSettings 未做 null check 导致 NPE",
    "fix_description_brief": "在第700行前增加 if (userSettings == null) return"
  }
}
```

飞书回复格式（`fix_status=diagnosed` 时，标题用 🔧 前缀）：
- 行 1：`服务: {service}  接口: {api_path}`
- 行 2：`原因: {root_cause_file}:{root_cause_line} — {why_npe}`
- 行 3：`追溯: {trace_chain 摘要}`
- 行 4：`建议: {suggested_fix.description}`
- 行 5：`操作: {manual_steps 简写}`

**lark_reply_content 要求：**
- 用自然语言描述问题和修复，像给同事解释一样
- 包含：服务+接口、问题分析（根因在哪个文件哪行、为什么出错）、修复方案（改了什么、为什么这么改）
- `fix_status=diagnosed` 时，必须包含 `suggested_fix.code_diff` 和 `manual_steps`（让人工修复从 30min→5min）
- PR 链接由下游自动追加，不需要在这里写
- 修复失败时也要写，说明失败原因和建议的人工排查方向

**fix_status=duplicate 时的格式**（仅由 Orchestrator step4_dedup 生成，Worker 不再产出此状态）：

> 注：精准去重已移至 Orchestrator pipeline.py step4_dedup 统一处理（L3 + L2 跨轮/同批次），
> Worker 收到的 issue 一定是 actionable 的，无需再做重复检查。

### Dispatcher 验证点（Phase A → B 之间）

**Dispatcher 执行，零 Agent token：**
```bash
# 验证诊断结果中的文件是否真实存在
for file in diagnosis.fix_plan.changes[*].file:
    Glob(file)  # 不存在 → 标记幻构，跳过 Phase B

# 验证行号是否合理
Read(file, offset=line-5, limit=10)  # 看看那行代码是不是诊断描述的样子
```

**Phase B 完成后（Dispatcher 执行）：**
```bash
# 验证编译通过
Read(fix-result.json)  # compile_status == "BUILD SUCCESS"

# 验证远端分支存在
git ls-remote origin refs/heads/{branch_name}
```

## 核心原则

**不仅止血，更要找到伤口来源**

修复 bug 分为三个层级：
1. **症状修复**：在当前模块加防御（try-catch、参数校验），快速止血，但根本问题未解决
2. **根本修复**：定位并修复数据源头问题（上游服务 bug、数据库脏数据、配置错误）
3. **混合修复**：当前模块加防御（立即止血）+ 提供根源追踪报告（后续根治）

**要求**：
- 症状修复必须配套"根源追踪行动"报告
- 不得只加 try-catch 就声称"已修复"
- 必须明确标注修复层级和遗留问题

### 常见反面案例（必须避免）

| 错误做法 | 正确做法 |
|---------|---------|
| 在 Controller A 给 IDTools.toLong() 加 try-catch | 修改 IDTools.toLong() 源码加输入校验 |
| 给每个 Dubbo RPC 调用加 try-catch 捕获 RejectedExecutionException | 标记为基础设施问题，建议调整线程池配置 |
| Dubbo Payload 超限时 try-catch 返回空值 | 改为分批查询控制单次 RPC 数据量 |
| catch(IOException) 改为 catch(Exception) | 查明为什么抛出了非 IOException（Hutool 包装问题），在调用层做类型适配 |

## 服务路径映射（monorepo 内硬编码）

整个 secondme monorepo（`kernel/` + `biz/`）均在修复范围内。
**若服务名不在下表中，不直接判定为外部依赖，先 Glob 搜索确认。**

| K8s 服务名 | monorepo 内路径 | 备注 |
|-----------|----------------|------|
| os-main-inner-api / os-main-inner-prod | kernel/os-main/ | Java |
| os-main-out-prod | kernel/os-main/ | Java |
| os-main-runner-prod | kernel/os-main/ | Java |
| os-ws-api-prodk8sNew | kernel/os-ws/ | Java |
| os-ws-websocket-prodk8sNew | kernel/os-ws/ | Java |
| os-ws-runner-prodk8sNew | kernel/os-ws/ | Java |
| base-datahub-prod / base-datahub-api | kernel/base-datahub/ | Java |
| **mind-kernel** | **kernel/mind-kernel/** | **Python，monorepo 内！** |
| os-user-prodk8s | biz/os-user/ | Java |
| **god_of_life_memory** | **biz/god_of_life_memory/** | **在 monorepo 内！** |

## ⚠️ 模块结构参考（防止幻觉，必读）

### kernel/os-main/ 内部结构

**关键：没有 `os-main-service` 模块！** 业务逻辑代码在 `os-main-component` 中。

| 子模块 | 职责 | 文件数 | 代码路径 |
|--------|------|--------|---------|
| os-main-sdk | 共享模型/常量/异常 | ~209 | `os-main-sdk/src/main/java/com/mindverse/os/main/sdk/` |
| **os-main-component** | **核心业务逻辑（Service + DAO）** | **~2747 (69.8%)** | `os-main-component/src/main/java/com/mindverse/os/main/` |
| os-main-inner-api | REST 控制器 + DTO | ~704 | `os-main-inner-api/src/main/java/com/mindverse/os/main/` |
| os-main-out-api | Dubbo RPC 服务 | ~212 | `os-main-out-api/src/main/java/com/mindverse/os/main/` |
| os-main-runner | MQ 消费者/定时任务 | ~244 | `os-main-runner/src/main/java/com/mindverse/os/main/` |

**基础包名**：`com.mindverse.os.main`（不是 `com.mindverse.os`）

**典型业务代码路径**：
- Service 实现：`kernel/os-main/os-main-component/src/main/java/com/mindverse/os/main/{domain}/service/impl/{Xxx}ServiceImpl.java`
- DAO 层：`kernel/os-main/os-main-component/src/main/java/com/mindverse/os/main/{domain}/dao/`
- REST 控制器：`kernel/os-main/os-main-inner-api/src/main/java/com/mindverse/os/main/{domain}/api/{Xxx}Controller.java`
- 全局异常处理：`kernel/os-main/os-main-inner-api/src/main/java/com/mindverse/os/main/sys/advice/GlobalExceptionHandler.java`

**常见业务域（{domain}）**：message, homepage, friend, circle, mind, session, user, chat, im, media, search, notification, ...（共 143+ 个域）

### kernel/os-ws/ 内部结构

| 子模块 | 职责 |
|--------|------|
| os-ws-sdk | 共享模型 |
| os-ws-component | 核心业务逻辑 |
| os-ws-api | REST + WebSocket 控制器 |
| os-ws-runner | MQ 消费者 |

### kernel/base-datahub/ 内部结构

| 子模块 | 职责 |
|--------|------|
| base-datahub-sdk | 共享模型 |
| base-datahub-component | 核心业务逻辑 |
| base-datahub-api | REST 控制器 |
| base-datahub-runner | MQ 消费者 |

### 定位代码的正确方法

**绝对禁止猜测文件路径！** 必须用 Grep 搜索：

```bash
# 1. 通过 subcode 定位抛出点
Grep(pattern="subcode关键词", path="kernel/os-main/", type="java")

# 2. 通过类名定位文件
Grep(pattern="class XxxServiceImpl", path="kernel/os-main/", type="java")

# 3. 通过方法名定位
Grep(pattern="methodName", path="kernel/os-main/os-main-component/", type="java")
```

**验证文件存在后再写入 diagnosis.json！**

## 输入参数

| 参数 | 说明 | 来源 |
|------|------|------|
| phase | 执行阶段：diagnose / fix / full（默认） | orchestrator |
| issue_id | 问题编号 | orchestrator |
| output_dir | 输出文件目录（默认 /tmp/worker/{issue_id}/） | orchestrator |
| message_id | 飞书告警消息 ID | orchestrator |
| traceId | 请求追踪 ID | orchestrator |
| alert_time | 告警时间戳（毫秒） | orchestrator |
| subcode | 错误子码 | orchestrator |
| api_path | 接口路径 | orchestrator |
| service | 服务名 | orchestrator |
| service_path | monorepo 内路径 | orchestrator |
| branch_name | 分支名 | orchestrator |
| compile_cmd | 编译命令 | orchestrator |
| cls_summary | CLS 日志摘要（Triager 预查询） | orchestrator |
| stack_trace_top3 | 堆栈前3行（Triager 预查询） | orchestrator |
| raw_logs | 原始日志片段（正则不匹配时的 fallback） | orchestrator |
| skip_env_check | 是否跳过环境检查 | orchestrator |
| skip_thread_reply | 是否跳过话题回复（true） | orchestrator |
| skip_feishu_write | 是否跳过飞书表格写入（true） | orchestrator |
| bitable_refs | 历史 bitable 参考记录列表 JSON（含 is_precise 字段） | orchestrator（可选） |

## Instructions

作为子 agent 执行单个问题的修复流程，禁止创建新子 agent。

### Phase A: 诊断（phase=diagnose）

**注意：Phase A 是只读操作，不需要 worktree 隔离。**

1. 输出中文；进入工作目录：
   - **优先检查当前目录**：若当前目录已是 monorepo（存在 `kernel/` 和 `biz/` 子目录），无需 cd
   - 若以上不满足：`cd $MONOREPO_DIR; pwd`（默认 `/Users/songxuexian/IdeaProjects/mindverse02/secondme`）

2. **分析错误日志**：
   - **如果 orchestrator 已提供 `cls_summary` 和 `stack_trace_top3`**：直接使用，**不要重复查询 CLS**
   - **如果 cls_summary 为空但 orchestrator 提供了 `raw_logs`**：用 raw_logs 辅助分析，从中提取错误关键词、类名、方法名等线索
   - **仅当 cls_summary 为空且有 traceId 且无 raw_logs 时**：使用 cls-log-query tid 追踪模式查询
   - 时间范围：alert_time 前后各5分钟
   - **即使所有日志信息为空，也不放弃**：继续 Step 3 用 subcode 搜索代码

3. **定位根因代码**（多级 fallback 策略，必须至少执行一级）：

   **3a. 有堆栈（stack_trace_top3 非空）**：
   - 从堆栈前3行识别第一个业务代码调用点
   - 根据服务路径映射定位 monorepo 中位置
   - **必须用 Grep/Glob 验证文件存在**，禁止猜测文件路径
   - Read 目标文件相关代码行，确认根因

   **3b. 无堆栈有 subcode（关键新增）**：
   - **必须 Grep 搜索 subcode 在 service_path 下的抛出位置**
   - 搜索策略（按优先级执行，直到找到结果）：
     1. 完整 subcode：`Grep(pattern="{subcode}", path="{service_path}", type="java")`
     2. 按 `.` 拆分搜索最后一段：如 `unexpected.error` → 搜索 `"unexpected.error"`，再搜索 `"unexpected"`
     3. 扩大范围到整个 monorepo：`Grep(pattern="{subcode}", type="java")`
   - 找到抛出点后 Read 上下文 50 行，理解抛出条件

   **3c. 无堆栈无 subcode**：
   - 用 api_path 反查 Controller：`Grep(pattern="api_path最后两段", path="{service_path}", type="java")`
   - 找到 Controller 后 Read 对应方法

   **3d. 全部搜索无结果**：
   - 标记 `search_exhausted: true`
   - 在 search_evidence 中列出所有已执行的搜索命令和结果

3.5. **全 monorepo 根因追溯**（找到抛出点后必须执行，能追就必须追）：

   **核心原则**：整个 secondme monorepo（`kernel/` + `biz/`）都是 Worker 的代码搜索和修复范围。
   调用链能往上追就必须往上追，直到遇到真正不在 monorepo 内的外部系统才停止。

   **判断"外部依赖"的唯一标准**：
   - ✅ 真正外部（可停止追溯）：OpenAI API / AWS / 微信 API / 腾讯 SMS / ES 托管服务 等真正第三方系统
   - ❌ 伪外部（必须继续追溯）：mind-kernel、god_of_life_memory 等虽然是独立微服务但在 secondme 仓库内

   **跨服务追溯步骤**：
   1. 在当前服务找到调用失败点（如 MindKernelInterface.java 调用 /v0.1/embeddings）
   2. 定位 monorepo 内对应服务代码：
      - 优先查 SERVICE_PATH_MAP（from config.py，已含 mind-kernel / god_of_life_memory 等）
      - 若不在 MAP 中：**先** Glob 搜索 `{MONOREPO_DIR}/**/{service_name}/` 判断是否在 monorepo 内
        - 找到 → 追溯进去继续分析
        - 找不到 → 才记录为真正外部依赖
   3. 读取上游服务的实现代码，继续往上追：
      a) 若上游代码有 Bug → 修改上游服务代码 + 提 PR（Python 服务用 git，不用 mvn）
      b) 若上游服务调用真正外部 API 失败 → 这才是真正外部依赖，记录根因并停止
      c) 若上游服务缺少兜底处理 → 可在上游服务加 fallback/retry
   4. diagnosis.json 中必须记录完整追溯链：
      ```json
      "upstream_trace": [
        { "layer": 1, "service": "base-datahub", "file": "MindKernelInterface.java:120", "finding": "调用 /v0.1/embeddings 返回 null" },
        { "layer": 2, "service": "mind-kernel", "file": "mind/embeddings/openai.py:45", "finding": "调用 OpenAI text-embedding-3-small API，HTTP 429 配额超限" },
        { "layer": 3, "service": "OpenAI", "finding": "真正外部依赖，追溯终止" }
      ]
      ```

   **必须 Read 至少 2 个文件**：抛出点文件 + 调用方/上游文件。

4. **制定修复计划**：
   - 记录 old_code（从文件中实际读取的）和 new_code
   - 记录编译命令
   - **不可修复时**：fix_plan.type 设为 `"无法修复"`，changes 设为空数组 `[]`，说明原因

5. **输出 diagnosis.json**：
   ```bash
   Write("{output_dir}/diagnosis.json", JSON(diagnosis))
   ```
   输出完整回执并结束。

### Phase B: 修复+编译+提交+推送（phase=fix）

**注意：Phase B 需要 worktree 隔离（修改代码）。所有操作在同一个 worktree 内完成。**

1. 读取 `{output_dir}/diagnosis.json`
2. 进入工作目录（worktree 根目录）
2.5. **验证 git 环境**（worktree 内必须执行）：
   ```bash
   git remote -v           # 确认 remote 存在
   git config user.email   # 确认身份配置
   ```
   - 若 remote 不存在 → 执行：
     `git remote add origin git@github.com:second-me-01/secondme.git`
   - 若 user.email 未配置 → 执行：
     `git config user.email "bot@mindverse.ai" && git config user.name "Claude Bot"`
3. 创建分支：`git checkout -b {branch_name}`
4. 按 diagnosis.json 中的 fix_plan 逐个修改文件
5. Maven 编译（必须加 `-Dmaven.gitcommitid.skip=true`）：
   ```bash
   {compile_cmd} 2>&1 | tail -80
   ```
6. 如果编译失败：写入 fix-result.json（compile_status: "BUILD FAILURE"）并结束
7. git add + git commit（提交规范：`fix(<module>): <issue-slug>`）
8. git push -u origin {branch_name}
9. **计算精准 fingerprint** 并写入 fix-result.json：
   - 读取 diagnosis.json 的 `root_cause.file`（取 basename，如 `"MindController.java"`）和 `root_cause.line`
   - 拼接：`precise_fingerprint = "{issue.fingerprint}_{ShortFilename}:{line}"`
     例：`os-main-inner-api_mind-public-profile_unexpected.error_MindController.java:548`
   - 若 root_cause 缺少 file/line，则 `precise_fingerprint = issue.fingerprint`（回退粗值）
   ```bash
   Write("{output_dir}/fix-result.json", JSON(fix_result))
   # fix-result.json 必须包含 precise_fingerprint 字段
   ```

### Phase Full: 全流程（phase=full，向后兼容）

执行 Phase A + B 全部步骤，不分阶段。适用于上下文充裕、问题简单的场景。

## 诊断质量底线

**diagnosis.json 必须通过以下检查，否则被 Dispatcher 拒绝：**

1. **文件大小**: diagnosis.json ≥ 500 字节（低于说明内容过于草率）
2. **root_cause 格式**: 必须是对象 `{file, method, line, description}`，字符串 → 拒绝
3. **fix_plan 格式**: 必须是对象，null → 拒绝
4. **search_evidence**: 无 stack_trace 且无 search_evidence → 拒绝（说明没搜索代码就放弃了）
5. **禁止自创字段**: 出现 category / fixable / is_external / skip_reason 等非规范字段 → 拒绝

**如果你认为问题无法修复，正确做法是：**
- 完成所有搜索步骤（Step 3a/3b/3c/3d）
- 在 search_evidence 中记录每一步搜索的命令和结果
- root_cause 填写找到的抛出点信息
- fix_plan.type 设为 `"无法修复"`，changes 设为空数组
- **绝对不允许跳过搜索直接声称"无法修复"**

## 编码规范

**层级职责**:
- Controller: 参数校验，无业务逻辑
- Service: 业务逻辑，禁止写 SQL/wrapper
- DAO: 构建 SQL/wrapper 并查询

**MyBatis Plus**: 使用 LambdaQueryWrapper/LambdaUpdateWrapper

**异常处理**: Service 抛 MoreException: `MoreException.onError(1, "module.action.error", message)`

**日志**: error=影响业务, warn=不影响业务, info=正常流程

## Maven 编译

⚠️ 必须添加 `-Dmaven.gitcommitid.skip=true`（worktree 使用 detached HEAD）

```bash
# os-main
mvn clean install -DskipTests -Ddockerfile.skip -Dmaven.gitcommitid.skip=true \
  -f kernel/os-main/pom.xml -pl os-main-inner-api -am \
  -s kernel/os-main/maven_package_settings.xml -gs kernel/os-main/maven_package_settings.xml \
  2>&1 | tail -80

# base-datahub
mvn clean install -DskipTests -Ddockerfile.skip -Dmaven.gitcommitid.skip=true \
  -f kernel/base-datahub/pom.xml -pl base-datahub-api -am \
  -s kernel/base-datahub/maven_package_settings.xml -gs kernel/base-datahub/maven_package_settings.xml \
  2>&1 | tail -80

# os-ws
mvn clean install -DskipTests -Ddockerfile.skip -Dmaven.gitcommitid.skip=true \
  -f kernel/os-ws/pom.xml -pl os-ws-api -am \
  -s kernel/os-ws/maven_package_settings.xml -gs kernel/os-ws/maven_package_settings.xml \
  2>&1 | tail -80

# os-user
mvn clean install -DskipTests -Ddockerfile.skip -Dmaven.gitcommitid.skip=true \
  -f biz/os-user/pom.xml -pl os-user-api -am \
  -s biz/os-user/maven_package_settings.xml -gs biz/os-user/maven_package_settings.xml \
  2>&1 | tail -80
```

## Git 操作

**严格禁止所有 force 操作**：
- `git push --force` / `git push -f`
- `git reset --hard`
- `git checkout -- .` / `git restore .`
- `git clean -f`
- `git worktree remove --force`

push 被拒绝 → `git pull --rebase` → 正常 push
需要回退 → `git revert` 创建新 commit
