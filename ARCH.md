# 架构设计（MVP）

## 1. 总体架构

系统采用本地 Web 应用架构：
- 前端：展示与操作（Inbox、Library、Daily）。
- 后端：文件扫描、ASR、标签抽取、归档、指令解析、打包、报告。
- 文件系统：作为主数据存储（音频、配置、报告）。

## 2. 组件划分

## 2.1 Frontend

- `Inbox` 页面：上传音频、查看识别结果、低置信手工修正。
- `Library` 页面：按 `VOCAB/SENTENCE/FASTSTORY` 浏览素材。
- `Daily` 页面：粘贴老师指令、解析需求、生成今日打包与报告。

## 2.2 Backend

- `scan_inbox()`：扫描 `Inbox` 新文件并入队。
- `process_audio(file)`：ASR -> 标签抽取 -> 归档。
- `parse_teacher_cmd(text)`：自然语言指令解析为结构化需求。
- `build_daily(date, needs)`：按需求复制 2 条 take 并输出报告。
- `logging`：记录关键处理链路与异常。

## 2.3 External Services

- ASR 引擎：`whisper_local` 或 `api`（配置切换）。
- LLM：仅在低置信或冲突时触发兜底分类。

## 3. 处理流程

## 3.1 音频处理流程

1. 检测新音频（上传或扫描）。
2. 获取时长与音频元信息。
3. 执行 ASR（用于标签识别时默认前 20 秒）。
4. 规则抽取：
   - 类型识别（VOCAB/SENTENCE/FASTSTORY）
   - 编号识别（中文/阿拉伯数字）
   - 标题识别（`mappings.json` 同义词）
   - 编号/标题互推
5. 输出标签与置信度。
6. 若 `confidence < 0.75` 或冲突，调用 LLM 兜底。
7. 按规范命名并归档到 `Library`。

## 3.2 每日打包流程

1. 用户输入老师指令文本。
2. 解析得到 `needs`（按类型的 index 列表）。
3. 遍历每个需求项，读取 `Library` 对应目录下所有 take。
4. 默认按时间戳选最新两条。
5. 复制到 `Daily/YYYY-MM-DD/<中文类型>/`。
6. 生成 `_report.txt`（覆盖率、缺遍、原始指令）。

## 4. 数据模型

核心记录字段：
- `id`
- `src_path`
- `duration_sec`
- `asr.engine`
- `asr.text`
- `asr.lang`
- `asr.segments`
- `tag.type`
- `tag.index`
- `tag.title_zh`
- `tag.title_en`
- `tag.confidence`
- `tag.signals`
- `library_path`

类型与范围：
- `VOCAB`：1..17
- `SENTENCE`：1..15
- `FASTSTORY`：1..6

## 5. 目录与命名规范

库目录示例：
- `Library/Vocab/C07_颜色(Color)/`
- `Library/Sentences/S05_数量相关(Quantity)/`
- `Library/FastStory/P03_A_super_player/`

命名规范：
- 库内 take：`take_YYYYMMDD_HHMMSS.m4a`
- 每日打包文件：`词汇_C07_颜色_take1.m4a`

## 6. 关键设计决策

- 规则优先：可解释、成本低。
- LLM 兜底：仅处理低置信与冲突，降低幻觉与费用。
- 文件系统优先：MVP 阶段快速落地、可人工核查。
- 日志必备：用于快速排查识别错误与缺遍原因。

