---
name: cls-log-query
description: 腾讯云 CLS 日志查询操作，支持参数化查询指定时间窗口的日志，包含已索引日志和 LogParseFailure 日志。支持逐服务模式和 tid 追踪模式。
---
# cls-log-query

### 核心信息
- **Region**: .env `$CLS_REGION`（默认 na-siliconvalley，❌ 不是 ap-guangzhou）
- **环境**: Silicon Valley Production
- **日志类型**: 已索引日志 + LogParseFailure 日志（解析失败的原始日志）

### 查询模式参数
- `per_service_mode`（默认 false）：true 时逐服务单独查询（8次 MCP 调用），适用于合并查询结果被截断的情况
- `tid`（可选）：指定 tid/traceId 值，触发跨服务全链路追踪模式（查询所有8个服务中匹配该 tid 的日志）
- `hours`（默认 2）：查询最近N小时
- `from` / `to`：指定时间范围（ISO 8601）

### 服务列表（Topic ID）
| 服务名 | Topic ID |
|--------|----------|
| base-datahub-prod | 4e474c78-eb40-4c64-aea6-f772db60919e |
| os-main-inner-prod | d15f227c-07ea-4614-853e-cbd55c83c146 |
| os-main-out-prod | 93e1a5ee-8a93-4a44-826c-9a8cdf8faa47 |
| os-main-runner-prod | 1d2e3d92-65bf-4122-8c00-5970bc99486c |
| os-user-prodk8s | 1bc167af-4d06-4485-9b7f-992fea4c8f90 |
| os-ws-websocket-prodk8sNew | 653ef067-534a-4ddd-a843-f0856898b0c2 |
| os-ws-api-prodk8sNew | bd5f8c6b-239b-4382-a7f7-1d3bfbcf4235 |
| os-ws-runner-prodk8sNew | 6e81487d-4daa-4dfa-95d0-4d02eb8e7c05 |

### 查询流程

**1. 计算查询时间窗口**
```
根据传入的参数计算查询时间范围：

选项A - 使用 hours 参数（查询最近N小时）：
  - 获取当前时间戳：current_time = ConvertTimestampToTimeString()
  - To = current_time（结束时间为当前时间）
  - From = To - (hours * 3600000)（开始时间向前推N小时）
  - 默认：hours = 2（查询最近2小时）

选项B - 使用 from/to 参数（查询指定时间范围）：
  - From = ConvertTimeStringToTimestamp(from_time)
  - To = ConvertTimeStringToTimestamp(to_time)
  - 用户必须提供有效的 ISO 8601 格式时间

动态调整窗口大小（可选）:
  - 如果任一服务返回日志数 >= 400: 缩小窗口至 1 小时
  - 如果任一服务返回日志数 >= 200: 缩小窗口至 30 分钟
  - 如果调整了窗口，输出提示并重新查询
  - 否则保持当前窗口大小
```

**2. 查询日志**

⚠️ **重要：使用 OR 逻辑一次性获取已索引日志和 LogParseFailure 日志**

```
【默认模式】对所有8个服务执行一次组合查询：

使用 mcp__cls-mcp-server__SearchLog 工具：
{
  "TopicId": "<服务 Topic ID>",
  "Region": "$CLS_REGION",
  "From": <开始时间戳>,
  "To": <结束时间戳>,
  "Query": "(<查询条件>) OR __TAG__.LogParseFailure:*",
  "Limit": 100,
  "Sort": "desc"
}

查询说明：
  - 使用 OR 逻辑同时查询已索引日志和 LogParseFailure 日志
  - 已索引日志：满足查询条件（例如：全文搜索 "ERROR" 并排除 MoreException）
  - LogParseFailure 日志：所有解析失败的原始日志
  - 一次查询获取完整结果，无需合并和去重
  - 按时间倒序排列
  - Limit 使用 100（减少 MCP 截断风险）

遍历所有8个服务，汇总日志结果。
```

**截断检测与逐服务模式（per_service_mode）**
```
判断结果是否被截断：
  - 总返回行数明显少于预期 OR
  - 部分服务返回 0 条但实际应有日志 OR
  - 调用方传入 per_service_mode=true

若检测到截断，切换为逐服务查询：
  → 对每个服务单独发起一次 MCP 调用（共8次）
  → 每次 Limit=100
  → 合并并去重所有结果（按 tid+exception 去重）
  → 输出提示："⚠️ 已切换逐服务查询模式（检测到结果截断）"
```

**tid 跨服务全链路追踪模式（bug-fix 流程主要使用此模式）**

> bug-fix 流程从飞书告警消息中直接获取 traceId，用 tid 精准查询即可，不需要全文搜索 ERROR。

```
当传入 tid 参数时，触发 tid 追踪模式：
  → 对所有8个服务分别查询：Query = "<tid_value>"
  → 时间范围：alert_time 前后各5分钟
  → Sort: "asc"（按时间升序，便于找根因）
  → 合并结果，获取完整调用链（请求入口 → 各服务处理 → 错误点）
  → 找出时间最早的 ERROR/WARN = 根因服务候选
  → 输出完整调用链时序 + 错误堆栈

注意：tid 精准查询能直接命中该请求在所有服务中的完整日志链路，
包括正常的请求/响应日志和异常堆栈，无需额外搜索。
```

**为什么使用 OR 组合查询？**

CLS 的索引机制会将日志分为两类：
1. **已索引日志**：成功解析并建立索引的日志，通过全文搜索查询（如 `"ERROR"`）
   - ⚠️ **`level` 字段未建索引**，不可使用 `level:error` 语法，必须用全文搜索 `"ERROR"`
2. **LogParseFailure 日志**：解析失败的原始日志，只能通过 `__TAG__.LogParseFailure` 查询

使用 OR 逻辑可以：
- ✅ 一次查询获取两种日志，避免遗漏
- ✅ 性能提升约 50%（无需执行两次查询）
- ✅ 简化逻辑（无需合并和去重）

**3. 提取和格式化日志（每个唯一 fingerprint 仅保留3行代表样本）**
```
对每条日志提取以下字段：

已索引日志（查询A）：
- 服务名 (service name)
- 异常类 (exception class)
- 错误消息 (message)
- 堆栈跟踪前3行（仅取每个唯一 fingerprint 的前3行作为代表样本）
- 追踪ID (tid/traceId)

LogParseFailure 日志（查询B）：
- 服务名 (service name)
- 原始日志内容 (__CONTENT__)
- 解析失败原因（如果有）
- 追踪ID (tid/traceId) - 尝试从原始内容中提取
- 标记：[LogParseFailure]

去重与精简规则：
- 对相同 fingerprint（相同异常类 + 相同堆栈前3行）的日志：只保留最新一条的前3行作为代表样本
- 同一异常在多个服务出现：每个服务各保留一条3行代表样本
- 目标：每条错误用3行定位，不展示完整堆栈（完整堆栈通过 tid 追踪获取）

格式化输出：
- 按服务分组
- 每个服务显示日志数量（已索引 + LogParseFailure）
- 输出汇总统计（总日志数、涉及服务数、LogParseFailure 日志数）
```

**4. 输出查询结果**
```
输出格式：
═══════════ 查询结果 ═══════════
查询时间：<From> - <To>（<X>小时）
总日志数：<N>（已索引：<N1>，LogParseFailure：<N2>）
涉及服务：<M>个

按服务分组：
- base-datahub-prod: <N1> 条（已索引：<N1a>，LogParseFailure：<N1b>）
- os-main-inner-prod: <N2> 条（已索引：<N2a>，LogParseFailure：<N2b>）
- ...

详细日志：

[已索引日志]
[服务名] [异常类] [tid]
<错误消息>
<堆栈跟踪前5-10行>
---

[LogParseFailure 日志]
[服务名] [LogParseFailure] [tid]
<原始日志内容>
解析失败原因：<原因>
---
```

### Bug 修复查询方式

**告警群消费模式（主流程）：直接用 tid 精准查询**
- 从飞书告警消息中提取 traceId
- 调用 cls-log-query tid 模式：`Query = "<traceId>"`
- 查询所有8个服务，获取完整调用链
- **不需要全文搜索 ERROR，tid 就是最精准的查询条件**

**独立日志扫描模式（仅用于 log-query-sv-prod 独立调用）：**
```
("ERROR" AND NOT "com.mindverse.os.framework.sdk.exception.MoreException" AND NOT "com.mindverse.os.main.sdk.exception.MoreExceptio") OR __TAG__.LogParseFailure:*
```

**查询说明**:
- ⚠️ **`level` 字段未建索引**，禁止使用 `level:error`，必须用全文搜索 `"ERROR"`
- 使用括号 `()` 将已索引日志的条件分组
- 使用 `OR` 连接 LogParseFailure 日志查询
- 第二个 NOT 字符串末尾缺少 "n" 是正确的，不要补全
- 一次查询同时获取两种类型的日志

### 必须提取的字段

**已索引日志：**
1. 服务名 (service name)
2. 异常类 (exception class)
3. 错误消息 (message)
4. 堆栈跟踪前3行（每个 fingerprint 仅保留3行代表样本；需要完整链路时通过 tid 追踪）
5. 追踪ID (tid/traceId)

### 时间范围（动态调整）
- 默认窗口: 2小时 (7200000 毫秒)
- 调整后窗口: 1小时 (3600000 毫秒)
- 最小窗口: 30分钟 (1800000 毫秒)
- 最大查询范围: 建议不超过24小时

### 查询语法

**日志查询语法：**
```
基本:
- "ERROR" (全文搜索，⚠️ level 字段未建索引，禁止使用 level:error)
- "keyword" (内容包含)
- AND / OR / NOT (逻辑)

组合:
- "ERROR" AND "NPE"
- "ERROR" AND NOT "expected"
```

### 错误处理
- TopicNotExist → 检查 Region (应为 na-siliconvalley)
- MCP 失败 → 记录原因，不得伪造结果
- 查询超时 → 尝试缩小时间窗口重试
- 日志过多（>1000条）→ 建议缩小时间范围
- LogParseFailure 查询失败 → 记录警告，继续使用已索引日志（但提示可能遗漏部分日志）

### 性能说明

**查询性能：**
```
使用组合查询（OR 逻辑）的性能优势：
- 单服务查询时间：约 1-2 秒
- 8个服务总查询时间：约 4-12 秒
- 比双重查询方式快约 50%（无需执行两次查询）
- 无需合并和去重，逻辑更简单
```

### 时间格式转换

**使用 MCP 工具进行时间转换：**

```
获取当前时间戳（毫秒）：
mcp__cls-mcp-server__ConvertTimestampToTimeString
{
  // 不传 timestamp 参数，返回当前时间
}

时间字符串转时间戳：
mcp__cls-mcp-server__ConvertTimeStringToTimestamp
{
  "timeString": "2026-01-27T10:00:00Z",
  "timeFormat": "YYYY-MM-DDTHH:mm:ss.sssZ",
  "timeZone": "Asia/Shanghai"
}

时间戳转时间字符串：
mcp__cls-mcp-server__ConvertTimestampToTimeString
{
  "timestamp": 1737964800000,
  "timeFormat": "YYYY-MM-DDTHH:mm:ss.sssZ",
  "timeZone": "Asia/Shanghai"
}
```

### 示例调用

**查询最近2小时（包含 LogParseFailure）：**
```
1. 不传任何参数，默认查询最近2小时
2. 对每个服务执行一次组合查询（已索引 + LogParseFailure）
3. 输出总日志数（已索引 + LogParseFailure）
```

**查询最近6小时：**
```
传入参数 hours=6
对每个服务执行一次组合查询
```

**查询指定时间范围：**
```
传入参数：
- from="2026-01-27T10:00:00Z"
- to="2026-01-27T12:00:00Z"
对每个服务执行一次组合查询
```

### 完整查询示例

```
对于服务 os-main-inner-prod (Topic ID: d15f227c-07ea-4614-853e-cbd55c83c146):

组合查询（已索引日志 + LogParseFailure 日志）：
mcp__cls-mcp-server__SearchLog({
  "TopicId": "d15f227c-07ea-4614-853e-cbd55c83c146",
  "Region": "$CLS_REGION",
  "From": 1737957600000,
  "To": 1737964800000,
  "Query": "(\"ERROR\" AND NOT \"com.mindverse.os.framework.sdk.exception.MoreException\" AND NOT \"com.mindverse.os.main.sdk.exception.MoreExceptio\") OR __TAG__.LogParseFailure:*",
  "Limit": 500,
  "Sort": "desc"
})

查询结果：
os-main-inner-prod: 18条日志（已索引：15，LogParseFailure：3）
```
