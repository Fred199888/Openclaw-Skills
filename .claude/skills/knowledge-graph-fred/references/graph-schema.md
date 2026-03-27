# Knowledge Graph JSON Schema

## 文件路径
`~/.claude/knowledge-graph/<project>/graph.json`

其中 `<project>` 是项目名（从 repo 目录名推导，如 `secondme`、`my-app`）。

## 顶层结构

```json
{
  "version": "1.0",
  "project": "<project-name>",
  "repo_path": "<absolute repo path>",
  "last_updated": "<ISO 8601 timestamp>",
  "files": { ... },
  "apis": { ... },
  "domains": { ... }
}
```

## files — 文件维度

key: 相对于 repo root 的文件路径

```json
{
  "files": {
    "src/services/UserService.java": {
      "domain": "user",
      "touch_history": [
        {
          "issue_id": "MIN-147",
          "date": "2026-02-27",
          "change_summary": "修复 getProfile() NPE，添加 null check",
          "lines_changed": "+15 -3"
        }
      ]
    }
  }
}
```

### touch_history 条目字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| issue_id | string | 是 | Linear issue ID |
| date | string | 是 | YYYY-MM-DD 格式 |
| change_summary | string | 是 | 修改内容的简短描述 |
| lines_changed | string | 否 | 如 "+15 -3" |

## apis — API 维度

key: `METHOD /path`（如 `GET /v1/users/{userId}`）

```json
{
  "apis": {
    "GET /v1/users/{userId}": {
      "handler_files": [
        "src/controllers/UserController.java",
        "src/services/UserService.java"
      ],
      "touch_history": [
        {
          "issue_id": "MIN-147",
          "date": "2026-02-27",
          "change_summary": "修复 NPE"
        }
      ]
    }
  }
}
```

### API 条目字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| handler_files | string[] | 否 | 处理该 API 的相关文件列表 |
| touch_history | array | 是 | 修改历史记录 |

## domains — 领域维度

key: domain 名（从文件路径推断，如 `user`、`auth`、`payment`）

```json
{
  "domains": {
    "user": {
      "key_files": [
        "src/services/UserService.java",
        "src/controllers/UserController.java"
      ],
      "related_issues": ["MIN-147", "MIN-152"],
      "known_pain_points": [
        "profile 字段可能为空，调用前需判空"
      ]
    }
  }
}
```

### Domain 条目字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| key_files | string[] | 是 | 该领域的关键文件列表（去重） |
| related_issues | string[] | 是 | 相关的 Linear issue ID 列表（去重） |
| known_pain_points | string[] | 否 | 已知的坑和注意事项 |

## 初始空结构

首次写入时自动创建：

```json
{
  "version": "1.0",
  "project": "<project-name>",
  "repo_path": "<absolute repo path>",
  "last_updated": "",
  "files": {},
  "apis": {},
  "domains": {}
}
```

## 更新规则

1. **追加而非覆盖** — touch_history 只追加，不删除历史记录
2. **按 issue_id 去重** — 同一 issue_id 对同一文件/API 只保留一条记录（后者覆盖前者）
3. **key_files 和 related_issues 去重** — 使用 Set 语义
4. **last_updated** — 每次写入时更新为当前时间
