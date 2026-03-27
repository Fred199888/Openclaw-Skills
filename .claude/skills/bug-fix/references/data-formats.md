# 数据格式定义

## 文件通信目录结构

```
/tmp/bugfix/{round}/
├── scan-result.json              # scanner.py 输出
├── precheck-result.json          # bitable_precheck.py 输出
├── cls-results.json              # cls_query.py 输出
├── triage-result.json            # triage.py 分类输出
├── triage-reply-result.json      # lark_reply.py triage 输出
├── worker-results.json           # Dispatcher 汇总写入
├── fix/
│   ├── I001/
│   │   ├── diagnosis.json        # Worker Phase A 输出
│   │   └── fix-result.json       # Worker Phase B 输出
│   ├── I002/
│   │   └── ...
├── report-result.json            # reporter.py 输出
└── round-summary.json            # Dispatcher 写入
```

## scan-result.json（scanner.py 输出）

scanner 读取最新 100 条消息，解析字段，不做去重。去重由下游 bitable_precheck（历史去重）和 CLS 查询后按堆栈位置精准去重。

```json
{
  "total_read": 100,
  "collected_count": 100,
  "business_expected": [
    {
      "issue_id": "I001",
      "message_id": "om_xxx",
      "service": "os-main",
      "service_path": "kernel/os-main/",
      "api_path": "/rest/os/user/token",
      "subcode": "token.expired",
      "traceId": "abc123",
      "alert_time": "1772164368656",
      "cls_topic_id": ""
    }
  ],
  "new_issues": [
    {
      "issue_id": "I002",
      "message_id": "om_yyy",
      "service": "os-main",
      "service_path": "kernel/os-main/",
      "api_path": "/rest/os/homepage/cover/to/video",
      "subcode": "unexpected.error",
      "traceId": "def456",
      "alert_time": "1772164368656",
      "cls_topic_id": "d15f227c-..."
    }
  ],
  "errors": []
}
```

**字段说明**：
- `new_issues`：所有非业务预期的告警消息，每条分配 issue_id（I001, I002...）
- `business_expected`：业务预期错误码（如 token.expired），无需修复

## precheck-result.json（precheck.py 输出）

在 scan-result.json 基础上，匹配多维表格历史记录作为参考。去重在 Phase 1 的 pipeline.py step4_dedup 完成。

```json
{
  "new_issues": [
    {
      "issue_id": "I003",
      "message_id": "om_xxx",
      "service": "os-main",
      "subcode": "new.error",
      "fingerprint": "os-main_api-path_new.error",
      "..."
    }
  ],
  "bitable_refs": {
    "I003": [
      {
        "record_id": "rec_zzz",
        "fingerprint": "os-main_api-path_new.error_SomeService.java:87",
        "is_precise": true,
        "任务名称": "new.error: 添加 null check",
        "状态": "已完成",
        "分支": "fix/cc/20260301/new-error",
        "root_cause_location": "SomeService.java NPE",
        "PR": "https://github.com/.../compare/master...fix/cc/20260301/new-error?expand=1"
      },
      {
        "record_id": "rec_aaa",
        "fingerprint": "os-main_api-path_new.error",
        "is_precise": false,
        "任务名称": "new.error: 诊断中",
        "状态": "已诊断",
        "分支": "",
        "root_cause_location": "SomeService.java 连接超时",
        "PR": ""
      }
    ]
  },
  "stats": {
    "total_scan_issues": 10,
    "ref_count": 1,
    "remaining_count": 10
  }
}
```

**字段说明**：
- `new_issues`：全部 issue（不再去重），全部进入 Phase 3 处理
- `bitable_refs`：参考信息字典（按 issue_id 索引），每条记录含 `is_precise` 布尔字段标识是否为精准 fingerprint。传给 Worker 用于 Step 2.5 精准去重
- `stats`：统计（total_scan_issues、ref_count、remaining_count）

**参考匹配规则**：
- 所有 bitable 记录按 coarse fingerprint 前缀聚合（精准 fp 截取前缀，粗 fp 原样作为 key）
- 每条记录标记 `is_precise`：末尾匹配 `_文件名.扩展名:行号`（正则 `_[A-Za-z][A-Za-z0-9]*\.[a-zA-Z]+:\d+$`）为 true，否则 false
- 精准去重在 Phase 1 pipeline.py step4_dedup 完成，Worker 不再执行去重

## cls-results.json（cls_query.py 输出）

```json
{
  "results": {
    "I001": {
      "issue_id": "I001",
      "cls_summary": "NPE at VideoService.java:123, param is null",
      "stack_trace_top3": "at com.mindverse.os.main...VideoService.convertToVideo(VideoService.java:123)\nat ...",
      "raw_logs_snippet": "",
      "log_count": 5,
      "query_status": "success"
    },
    "I002": {
      "issue_id": "I002",
      "cls_summary": "",
      "stack_trace_top3": "",
      "raw_logs_snippet": "",
      "log_count": 0,
      "query_status": "skipped_no_trace_id"
    },
    "I003": {
      "issue_id": "I003",
      "cls_summary": "",
      "stack_trace_top3": "",
      "raw_logs_snippet": "2026-03-01 10:00:00 ERROR [tid:abc123] embeddingsV3 call failed: connection timeout\n---\n2026-03-01 10:00:01 ERROR [tid:abc123] retry failed after 3 attempts",
      "log_count": 3,
      "query_status": "success"
    }
  }
}
```

**raw_logs_snippet 说明**：
- 当 stack_trace_top3 和 cls_summary 都为空（正则不匹配）但有原始日志时，拼接前 3 条日志内容（每条截取 500 字符），用 `\n---\n` 分隔
- 用途：传递给 Worker 作为 raw_logs 参数，辅助诊断

**query_status 枚举**:
- `success` — 查询成功且有日志
- `no_logs` — 查询成功但无日志
- `skipped_no_trace_id` — traceId 为空/N/A，跳过查询
- `skipped_unknown_service` — 服务名无法映射到 CLS Topic
- `topic_not_found` — CLS Topic 未找到

## triage-result.json（triage.py 分类输出）

```json
{
  "fix_issues": [
    {
      "issue_id": "I001",
      "message_id": "om_xxx",
      "service": "os-main",
      "service_path": "kernel/os-main/",
      "subcode": "image.convert.video.failed",
      "traceId": "abc123",
      "api_path": "/rest/os/homepage/cover/to/video",
      "alert_time": "1772164368656",
      "fingerprint": "os-main_os-homepage-cover-to-video_image.convert.video.failed",
      "category": "real_bug",
      "cls_summary": "NPE at VideoService.java:123, param is null",
      "stack_trace_top3": "at com.mindverse.os.main...VideoService.convertToVideo(VideoService.java:123)\nat ...",
      "raw_logs_snippet": ""
    }
  ],
  "non_code_issues": [
    {
      "issue_id": "I002",
      "message_id": "om_zzz",
      "fingerprint": "os-main_os-mind-profile_sql.injection",
      "subcode": "sql.injection",
      "category": "attack",
      "evidence": "请求参数包含注入/XSS/遍历特征"
    }
  ],
  "replies_sent": {}
}
```

**说明**：`replies_sent` 为空对象（triage 回复由 lark_reply.py 单独处理）

## triage-reply-result.json（lark_reply.py triage 输出）

```json
{
  "command": "triage",
  "replies_sent": {
    "business_expected": {"sent": 5, "failed": 0},
    "non_code": {"sent": 3, "failed": 0}
  },
  "replied_message_ids": ["om_aaa", "om_bbb", "om_ccc"]
}
```

**字段说明**：
- `replied_message_ids`：Phase 2 batch_reply.py 已回复的 message_id 列表

## diagnosis.json（Worker Phase A 输出）

路径: `/tmp/bugfix/{round}/fix/{issue_id}/diagnosis.json`

**可修复示例：**
```json
{
  "issue_id": "I001",
  "service": "os-main",
  "service_path": "kernel/os-main/",
  "root_cause": {
    "file": "kernel/os-main/os-main-component/src/.../MindController.java",
    "method": "getPublicProfile",
    "line": 548,
    "description": "simplePublicHomepage 可能为 null，访问 .getCover() 导致 NPE"
  },
  "fix_plan": {
    "type": "根本修复",
    "changes": [
      {
        "file": "kernel/os-main/os-main-component/src/.../MindController.java",
        "line_range": "548",
        "old_code": "String ogImage = StrUtil.isNotBlank(simplePublicHomepage.getCover()) ? ...",
        "new_code": "String ogImage = (simplePublicHomepage != null && StrUtil.isNotBlank(simplePublicHomepage.getCover())) ? ...",
        "reason": "添加 null check 防止 NPE"
      }
    ],
    "compile_cmd": "mvn clean install -DskipTests ..."
  },
  "search_evidence": [
    {"command": "Grep(pattern='unexpected.error', path='kernel/os-main/', type='java')", "result": "找到 3 处匹配"},
    {"command": "Read('kernel/os-main/.../MindController.java', offset=540, limit=20)", "result": "确认 line 548"}
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
  "service": "os-main",
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
    "reason": "根因在外部 EmbeddingsV3 API 服务端"
  },
  "search_evidence": [
    {"command": "Grep(pattern='embeddingsV3', path='kernel/os-main/', type='java')", "result": "EmbeddingsServiceImpl.java:123"},
    {"command": "Read('kernel/os-main/.../EmbeddingsServiceImpl.java', offset=110, limit=30)", "result": "确认为外部 HTTP 调用"}
  ],
  "upstream_analysis": {
    "root_in_monorepo": false,
    "upstream_service": "EmbeddingsV3 API",
    "tracking_actions": ["联系服务维护方"]
  }
}
```

**格式硬性要求（Dispatcher Phase 3A 验证）：**
- `root_cause` 必须是对象 `{file, method, line, description}`，不能是字符串
- `fix_plan` 必须是对象，不能是 null
- `search_evidence` 数组必须存在（无堆栈时必填）
- 禁止自创字段（category / fixable / is_external / skip_reason）
- 文件大小 ≥ 500 字节

## fix-result.json（Worker Phase B 输出，含 commit+push）

路径: `/tmp/bugfix/{round}/fix/{issue_id}/fix-result.json`

```json
{
  "issue_id": "I001",
  "fix_status": "success",
  "files_modified": ["kernel/os-main/os-main-component/src/.../MindController.java"],
  "compile_status": "BUILD SUCCESS",
  "branch": "fix/cc/20260227/unexpected-error",
  "commit": "d63f64a9",
  "push_status": "success",
  "reply_summary": {
    "fix_type": "已修复",
    "root_cause_brief": "simplePublicHomepage null 时访问 .getCover() 导致 NPE",
    "fix_description_brief": "添加 null check"
  },
  "lark_reply_content": "服务: os-main  接口: /rest/os/homepage/cover/to/video\n问题分析: MindController.java:548 行，simplePublicHomepage 可能为 null，直接调用 .getCover() 导致 NPE。当用户首页未设置封面时就会触发。\n修复方案: 在访问 getCover() 前增加 null 判断，simplePublicHomepage 为空时使用默认封面。"
}
```

**lark_reply_content 字段说明**：
- Worker（LLM）生成的自然语言回复文本，用于飞书话题回复
- 优先级高于模板回复（reply_summary），lark_reply.py 优先使用此字段
- 内容要求：像给同事解释一样，包含服务+接口、问题分析（根因文件+行号+原因）、修复方案
- PR 链接由 lark_reply.py 自动追加，不需要写在这里
- 修复失败时也需要写，说明失败原因和建议的人工排查方向

**fix_status=duplicate 时的格式**（由 Orchestrator Phase 1 step4_dedup 生成）：

```json
{
  "issue_id": "I005",
  "fix_status": "duplicate",
  "duplicate_of": {
    "record_id": "rec_xxx",
    "fingerprint": "os-main_api-path_old.error_ServiceImpl.java:87",
    "任务名称": "old.error: 添加 null check",
    "状态": "已完成",
    "分支": "fix/cc/20260301/old-error",
    "PR": "https://github.com/.../compare/master...fix/cc/20260301/old-error?expand=1"
  },
  "precise_fingerprint": "os-main_api-path_old.error_ServiceImpl.java:87",
  "reply_summary": {
    "fix_type": "去重",
    "root_cause_brief": "与历史修复记录相同代码位置",
    "fix_description_brief": "已在分支 fix/cc/20260301/old-error 中修复"
  }
}
```

飞书回复由 batch_reply.py Phase 2 统一处理，根据 triage 推导标题（⏳等待合并/ℹ️业务预期等）。

## worker-results.json（Dispatcher 汇总写入）

路径: `/tmp/bugfix/{round}/worker-results.json`

```json
{
  "I001": {
    "status": "success",
    "branch": "fix/cc/20260227/unexpected-error",
    "commit": "d63f64a9",
    "message_id": "om_xxx",
    "fingerprint": "os-main_os-homepage-cover-to-video_unexpected.error",
    "subcode": "unexpected.error",
    "reply_summary": {
      "fix_type": "已修复",
      "root_cause_brief": "simplePublicHomepage null 时访问 .getCover() 导致 NPE",
      "fix_description_brief": "添加 null check"
    },
    "lark_reply_content": "服务: os-main  接口: /rest/os/homepage/cover/to/video\n问题分析: MindController.java:548 行，simplePublicHomepage 可能为 null...\n修复方案: 增加 null 判断，为空时使用默认封面。"
  },
  "I003": {
    "status": "failed",
    "error": "hallucination",
    "message_id": "om_zzz",
    "fingerprint": "os-main_os-mind-search_some.error",
    "subcode": "some.error",
    "lark_reply_content": "服务: os-main  接口: /rest/os/mind/search\n问题分析: 诊断阶段未能定位到准确的代码位置，可能是外部依赖或配置问题。\n建议: 人工检查该接口的调用链路和外部服务依赖。"
  },
  "I004": {
    "status": "diagnosis_rejected",
    "error": "diagnosis.json < 500 bytes, root_cause 是字符串而非对象",
    "message_id": "om_aaa",
    "fingerprint": "os-main_os-mind-detail_some.error",
    "subcode": "some.error",
    "lark_reply_content": "服务: os-main  接口: /rest/os/mind/detail\n问题分析: Worker 诊断质量不合格（诊断内容过于简略），需人工排查。\n建议: 检查该接口的错误日志和调用链路。"
  }
}
```

**字段说明**：
- `lark_reply_content`：从 fix-result.json 透传，优先用于飞书话题回复
- `reply_summary`：模板回复的 fallback 数据，当 lark_reply_content 不存在时使用

## report-result.json（reporter.py 输出）

路径: `/tmp/bugfix/{round}/report-result.json`

```json
{
  "table_writes": {"success": 3, "failed": 0},
  "thread_replies": {
    "fixed": {"sent": 3, "failed": 0},
    "failed_fix": {"sent": 2, "failed": 0},
    "skipped": {"sent": 1, "failed": 0}
  },
  "stats": {
    "N": 5,
    "M": 3,
    "K": 20,
    "B": 2
  }
}
```

## round-summary.json（Dispatcher 写入）

路径: `/tmp/bugfix/{round}/round-summary.json`

```json
{
  "round": 1,
  "stats": {"N": 5, "M": 3, "K": 20, "B": 2},
  "timestamp": "2026-02-27T15:30:00+08:00"
}
```

## N/M/K/B/D/E 统计口径

- **N** = triage-result.json 中 fix_issues 数量（需要修复的 real_bug + unknown）
- **M** = worker-results.json 中 status=="success" 的数量
- **K** = triage-result.json 中 non_code_issues 数量 + scan-result.json 中 business_expected 数量
- **B** = worker-results.json 中 status=="failed" 的数量
- **D** = worker-results.json 中 status=="duplicate" 的数量（Phase 1 pipeline step4_dedup 去重）
- **E** = Phase 1.5 多维表格预查中已有记录的数量（bitable_existing_count）

## 飞书话题回复模板

所有回复模板按所属阶段分组，同一阶段内格式统一。

### Phase 2 — batch_reply.py 批量回复

Phase 2 在 Phase 1（pipeline.py）完成后、Phase 3（Worker）启动前执行，为所有非 actionable 消息发送飞书话题回复。

#### Scene A - 业务预期（business_expected）

纯文本格式，回复 scanner 识别出的业务预期错误码。

```json
{"text": "ℹ️ 业务预期错误码 ({subcode})，无需处理"}
```

#### Scene B - 非代码问题（non_code_issues）

富文本 post 格式，回复 triage 分类为攻击/偶发/unfixable 等非代码问题。

```json
{
  "zh_cn": {
    "title": "ℹ️ {category} | {subcode}",
    "content": [
      [{"tag": "text", "text": "服务: {service}  接口: {api_path}"}],
      [{"tag": "text", "text": "原因: {evidence}"}],
      [{"tag": "text", "text": "处理: 无需代码修复"}]
    ]
  }
}
```

### Worker Step 4 — 飞书话题回复

Worker 修复完成后在话题内回复，标题前缀用 ⏳等待合并（有 PR 时）或其他分类标题。

#### Scene D - 已修复（worker status=success，模板 fallback）

```json
{
  "zh_cn": {
    "title": "✅ 已修复 | {subcode}",
    "content": [
      [{"tag": "text", "text": "服务: {service}  接口: {api_path}"}],
      [{"tag": "text", "text": "原因: {root_cause_brief}"}],
      [{"tag": "text", "text": "处理: {fix_description_brief}"}],
      [{"tag": "text", "text": "PR: "}, {"tag": "a", "text": "{pr_url}", "href": "{pr_url}"}]
    ]
  }
}
```

#### Scene E - 无法自动修复（worker status=failed，模板 fallback）

```json
{
  "zh_cn": {
    "title": "❌ 无法自动修复 | {subcode}",
    "content": [
      [{"tag": "text", "text": "服务: {service}  接口: {api_path}"}],
      [{"tag": "text", "text": "原因: {error}"}],
      [{"tag": "text", "text": "处理: 需人工排查"}]
    ]
  }
}
```

#### Scene F - 跳过（worker status=skipped，模板 fallback）

```json
{
  "zh_cn": {
    "title": "ℹ️ 跳过 | {subcode}",
    "content": [
      [{"tag": "text", "text": "服务: {service}  接口: {api_path}"}],
      [{"tag": "text", "text": "原因: {reason}"}],
      [{"tag": "text", "text": "处理: 无需代码修复"}]
    ]
  }
}
```

#### Scene G — 去重消息（batch_reply.py Phase 2 处理）

去重消息的飞书回复由 batch_reply.py 统一处理，根据原始 issue 的实际分类继承标题：
- 有 PR → ⏳等待合并
- 业务预期 subcode → ℹ️业务预期
- 其他 → 用 triage 规则推导

## 飞书表格字段映射

| 表格字段名 | 来源 | 格式 | 类型 |
|-----------|------|------|------|
| 任务名称 | subcode + fix_description_brief | `"{subcode}: {fix_description_brief}"`；仅有 subcode 时 `"fix: {subcode}"` | 文本 |
| 服务名 | issue.service | | 文本 |
| 分支 | worker_result.branch | | 文本 |
| 状态 | 固定值 | `"已完成"` | 单选 |
| 优先级 | 固定值 | `"高"` | 单选 |
| 负责人 | 固定值 | `"Claude Code"` | 文本 |
| tid | issue.traceId | 无值时写 `"-"` | 文本 |
| PR | branch 拼接 | `"{GITHUB_REPO_URL}/compare/master...{branch}?expand=1"` | 文本 |
| issue_fingerprint | issue.fingerprint | | 文本 |
| root_cause_location | reply_summary.root_cause_brief | | 文本 |
| 完成时间 | 当前时间戳 | 毫秒数字 | 日期 |

**重要**: 飞书表格写入需要 `useUAT: true` 参数（MCP 模式），脚本模式使用 user_access_token 直接调用。
