# API 设计（MVP 草案）

说明：以下为本地后端接口草案，供实现 FastAPI/Node 时对齐。返回体示例采用 JSON。

## 1. 健康检查

## `GET /api/health`

用途：服务状态检查。  
返回：

```json
{
  "ok": true,
  "time": "2026-02-08T10:00:00Z",
  "asr_engine": "whisper_local",
  "asr_process_scope": "hybrid",
  "whisper_model": "small",
  "asr_tag_window_sec": 20
}
```

## 2. Inbox 上传与扫描

## `POST /api/inbox/upload`

用途：上传一个或多个音频文件到 `HomeworkVault/Inbox/`。  
请求：`multipart/form-data`（`files[]`）  
返回：

```json
{
  "saved": [
    { "name": "a.m4a", "path": "HomeworkVault/Inbox/a.m4a" }
  ]
}
```

## `POST /api/inbox/scan`

用途：扫描 `Inbox` 新音频并触发处理。  
返回：

```json
{ "queued": 3, "processed": 3, "failed": 0 }
```

## `GET /api/inbox/items`

用途：查询最近处理结果列表。  
返回字段：
- `file_name`
- `duration_sec`
- `type`
- `index`
- `title_zh`
- `title_en`
- `confidence`
- `library_path`
- `needs_review`

## 3. 音频处理与人工修正

## `POST /api/audio/process`

用途：指定单文件立即处理。  
请求：

```json
{ "path": "HomeworkVault/Inbox/a.m4a" }
```

返回：

```json
{
  "id": "uuid-or-hash",
  "tag": {
    "type": "VOCAB",
    "index": 7,
    "title_zh": "颜色",
    "title_en": "Color",
    "confidence": 0.86
  },
  "library_path": "HomeworkVault/Library/Vocab/C07_颜色(Color)/take_20260208_153012.m4a"
}
```

## `POST /api/asr/test`

用途：上传一条音频做 ASR 调试（不落库），返回完整转写、前 N 秒标签文本和标签预览。  
请求：`multipart/form-data`（`file`）  
可选查询参数：
- `tag_window_sec`：标签窗口秒数
- `scope`：`full|head|hybrid`
  - `full`：全量音频转写
  - `head`：仅转写前 `tag_window_sec` 秒（若本机无 `ffmpeg` 会回退到 `full`）
  - `hybrid`：全量音频转写 + 头部截断优化标签文本（对齐主流程默认）
返回：

```json
{
  "engine": "stub|whisper_local|openai_api",
  "lang": "zh",
  "duration_sec": 0.0,
  "scope": "full",
  "used_head_clip": false,
  "fallback_to_full": false,
  "timing_ms": {
    "head_clip": 0.0,
    "asr": 0.0,
    "total": 0.0
  },
  "asr_text": "...",
  "tag_window_text": "...",
  "segments": [{"t0": 0.0, "t1": 1.2, "text": "..."}],
  "tag_preview": {
    "type": "VOCAB",
    "index": 7,
    "title_zh": "颜色",
    "title_en": "Color",
    "confidence": 0.86,
    "signals": {}
  }
}
```

## `POST /api/audio/relabel`

用途：对低置信条目执行人工修正并更新归档。  
请求：

```json
{
  "id": "uuid-or-hash",
  "type": "VOCAB",
  "index": 7,
  "title_zh": "颜色",
  "title_en": "Color"
}
```

返回：

```json
{ "ok": true, "library_path": "HomeworkVault/Library/Vocab/C07_颜色(Color)/take_20260208_153012.m4a" }
```

## 4. Library 查询

## `GET /api/library/summary`

用途：按类型返回每个条目的统计。  
返回字段：
- `type`
- `index`
- `title_zh`
- `title_en`
- `take_count`
- `latest_time`

## `GET /api/library/takes`

用途：查询某条目 take 列表。  
查询参数：`type`, `index`  
返回：

```json
{
  "type": "SENTENCE",
  "index": 5,
  "takes": [
    { "name": "take_20260208_153012.m4a", "path": "..." }
  ]
}
```

## `GET /api/file`

用途：按项目相对路径读取文件（用于前端音频试听）。  
查询参数：`path`（必须位于 `HomeworkVault` 下）  
返回：文件流（`FileResponse`）

## `GET /api/text`

用途：读取 `HomeworkVault` 下文本文件（用于读取 `_report.txt`）。  
查询参数：`path`  
返回：

```json
{ "path": "HomeworkVault/Daily/2026-02-08/_report.txt", "text": "..." }
```

## `POST /api/open-folder`

用途：在本机打开 `HomeworkVault` 下目录（Windows 使用 explorer）。  
查询参数：`path`  
返回：

```json
{ "ok": true }
```

## `GET /api/structured/list`

用途：列出 `originalText/structured` 下可读取文件。  
返回：

```json
{ "files": ["vocab_17.json", "sentence_15.json", "faststory_6.json"] }
```

## `GET /api/structured/read`

用途：读取 `structured` 文件内容（json 或 txt）。  
查询参数：`path`（文件名）  
返回：`{path, data}` 或 `{path, text}`

## `POST /api/config/apply-seed`

用途：将 `originalText/structured/mappings_seed_from_originalText.json` 应用为运行配置。  
可选查询参数：`seed_file`（默认值为上面的文件名）  
返回：

```json
{ "ok": true }
```

## 5. 老师指令与 Daily

## `POST /api/teacher/parse`

用途：解析老师指令为当日需求。  
请求：

```json
{ "text": "句子五、句子8，词汇七和11，快嘴第三篇" }
```

返回：

```json
{
  "date": "2026-02-08",
  "needs": {
    "SENTENCE": [5, 8],
    "VOCAB": [7, 11],
    "FASTSTORY": [3]
  }
}
```

## `POST /api/daily/build`

用途：按需求生成 `Daily/YYYY-MM-DD/`。  
请求：

```json
{
  "date": "2026-02-08",
  "teacher_cmd": "句子五、句子8，词汇七和11，快嘴第三篇",
  "needs": {
    "SENTENCE": [5, 8],
    "VOCAB": [7, 11],
    "FASTSTORY": [3]
  }
}
```

返回：

```json
{
  "daily_dir": "HomeworkVault/Daily/2026-02-08/",
  "copied": 7,
  "missing": [
    { "type": "SENTENCE", "index": 8, "missing_count": 1 },
    { "type": "VOCAB", "index": 11, "missing_count": 2 }
  ],
  "report_path": "HomeworkVault/Daily/2026-02-08/_report.txt"
}
```

## 6. 配置接口（可选）

## `GET /api/config/mappings`

用途：读取 `mappings.json`。

## `PUT /api/config/mappings`

用途：更新 `mappings.json`（支持同义词微调）。

## 7. 错误码建议

- `400`：请求参数不合法（类型超范围、缺字段）。
- `404`：目标文件或条目不存在。
- `409`：标签冲突或重复处理冲突。
- `500`：ASR/LLM/文件系统异常。
