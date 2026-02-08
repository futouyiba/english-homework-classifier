# Homework Audio Agent 需求文档（MVP）

版本：v1.0（由 `homework_audio_agent_codx_prd.md` 拆分整理）  
日期：2026-02-08

## 1. 文档目标

将原始 PRD 拆分为可执行、可验收的需求规格，覆盖：
- 业务目标与范围
- 功能需求（带编号）
- 数据与目录规范
- 非功能需求
- MVP 验收标准

## 2. 业务目标与范围

### 2.1 目标

系统需要把孩子朗读音频自动归档到素材库，并根据老师当天微信群指令自动生成每日文件夹与缺遍报告。

### 2.2 场景约束

- 口播关键词可能存在，但顺序可能颠倒。
- 每条音频只对应一个条目的一遍。
- 同一条目可能有 2~4 遍，素材库需全量保留。
- 每日打包时每个条目只选 2 遍。

### 2.3 范围（MVP）

- 本地 Web UI（上传、查看、打包）。
- 后端流水线（扫描/处理/归档/打包）。
- 可配置 ASR（本地 Whisper 或云端 API）。
- 规则优先 + LLM 兜底的标签识别。
- 老师指令解析与报告生成。

### 2.4 非范围（MVP 不要求）

- 多用户权限体系。
- 云端部署与分布式扩展。
- 高级报表可视化。

## 3. 角色与核心流程

### 3.1 角色

- 家长/操作者：上传音频、粘贴老师指令、触发每日打包。
- 系统：自动识别、归档、打包、输出报告。

### 3.2 端到端流程

1. 音频进入 `Inbox`（上传或目录扫描）。
2. 系统执行 ASR 转写（优先用前 N 秒打标签）。
3. 系统抽取标签（类型/编号/标题/置信度）。
4. 低置信或冲突时调用 LLM 兜底分类。
5. 音频按规范落到 `Library` 对应目录。
6. 用户粘贴老师指令，系统解析当日需求。
7. 系统从 `Library` 选每条目最新 2 条复制到 `Daily/YYYY-MM-DD/`。
8. 系统生成覆盖率/缺遍报告。

## 4. 功能需求（Functional Requirements）

## 4.1 文件与目录管理

- FR-001：系统启动时必须自动创建标准目录结构（见第 6 章）。
- FR-002：系统必须支持 `Inbox` 目录扫描获取新音频。
- FR-003：系统必须支持 Web UI 多文件上传并落盘到 `Inbox`。

## 4.2 音频处理与转写

- FR-004：系统必须支持可配置的 ASR 引擎：`whisper_local` 或 `api`。
- FR-005：系统必须支持仅使用音频前 N 秒文本用于标签识别，默认 `N=20`，可配置。
- FR-006：系统必须保存完整转写文本；可选保存分段时间戳 `segments`。

## 4.3 标签识别（规则优先）

- FR-007：系统必须识别类型枚举：`VOCAB | SENTENCE | FASTSTORY`。
- FR-008：系统必须识别中英文混合关键词且不依赖口播顺序。
- FR-009：系统必须支持中文数字与阿拉伯数字编号识别。
- FR-010：系统必须基于 `mappings.json` 的 `title/synonyms` 做标题命中。
- FR-011：系统必须支持“编号/标题互推”补全标签信息。
- FR-012：系统必须输出置信度并记录命中信号（keywords/number/title forms）。

## 4.4 LLM 兜底分类

- FR-013：当 `confidence < 0.75` 或规则冲突时，系统必须触发 LLM 兜底。
- FR-014：LLM 输入必须携带“合法候选集合”，输出限定为 JSON 结构。
- FR-015：LLM 输出字段至少包含：`type/index/title_zh/title_en/confidence/notes`。

## 4.5 素材库归档

- FR-016：每条音频必须归档到 `Library` 的唯一目标目录（按 type+index）。
- FR-017：素材库中的 take 文件名必须使用时间戳：`take_YYYYMMDD_HHMMSS.m4a`。
- FR-018：系统必须保存音频元数据（来源、时长、ASR、标签、落库路径）。

## 4.6 老师指令解析

- FR-019：系统必须支持解析中文自然语言指令（含括号、顿号、空格、混合数字）。
- FR-020：系统必须按类型输出当日需求：`SENTENCE/VOCAB/FASTSTORY` 的 index 列表。
- FR-021：系统必须执行去重与排序。
- FR-022：系统必须支持括号内容二次提取（视为同类型追加项）。

## 4.7 每日打包与报告

- FR-023：系统必须按 `type+index` 从素材库选择“最新两条”take（按时间戳）。
- FR-024：系统必须复制到 `Daily/YYYY-MM-DD/<中文类型>/`。
- FR-025：每日文件命名必须固定、便于发送：
  - `词汇_C07_颜色_take1.m4a`
  - `词汇_C07_颜色_take2.m4a`
- FR-026：当可用 take 少于 2 条时，系统必须在报告中标记缺口数量。
- FR-027：系统必须生成 `_report.txt`，包含原始指令、需求清单、覆盖率与缺遍项。

## 4.8 Web UI

- FR-028：系统必须提供 3 个页面：`Inbox`、`Library`、`Daily`。
- FR-029：`Inbox` 页面必须展示：文件名、时长、识别结果（中英同行）、置信度、落库路径。
- FR-030：对低置信条目，UI 必须允许手动修改 `type/index/title`。
- FR-031：`Library` 页面必须支持三类 Tab 与条目卡片（编号、标题、take 数、最新时间）。
- FR-032：`Daily` 页面必须支持“解析指令”与“生成今日文件夹”两个动作，并展示报告结果。

## 4.9 配置与初始化

- FR-033：系统必须在 `HomeworkVault/Config/mappings.json` 提供默认映射。
- FR-034：默认映射需全量覆盖：`VOCAB 1..17`、`SENTENCE 1..15`、`FASTSTORY 1..6`。
- FR-035：系统必须支持后续手工调整 `synonyms`。

## 4.10 日志与可追溯性

- FR-036：系统必须记录关键日志：文件入队、ASR 成功/失败、规则命中、LLM 调用、落库路径、打包结果。
- FR-037：日志应支持定位“识别错误”与“缺遍原因”。

## 5. 数据需求

### 5.1 核心数据模型

最小字段要求：
- `id`
- `src_path`
- `duration_sec`
- `asr.engine/text/lang/segments`
- `tag.type/index/title_zh/title_en/confidence/signals`
- `library_path`

### 5.2 枚举与索引范围

- `Type`：`VOCAB | SENTENCE | FASTSTORY`
- `VOCAB` 索引范围：1..17
- `SENTENCE` 索引范围：1..15
- `FASTSTORY` 索引范围：1..6

## 6. 目录与命名规范

```text
HomeworkVault/
  Inbox/
  Library/
    Vocab/
    Sentences/
    FastStory/
  Daily/
  Config/
    mappings.json
    teacher_cmd.txt
  Reports/

app/
  backend/
  frontend/
```

库目录命名示例：
- `Library/Vocab/C07_颜色(Color)/`
- `Library/Sentences/S05_数量相关(Quantity)/`
- `Library/FastStory/P03_A_super_player/`

## 7. 非功能需求（NFR）

- NFR-001：支持本地运行（Windows 优先）。
- NFR-002：默认流程可在单机完成，不依赖云服务（云 ASR/LLM 可选）。
- NFR-003：规则引擎优先，LLM 调用需可控以降低成本。
- NFR-004：关键文件操作（复制/移动/重命名）需具备异常处理与日志。
- NFR-005：UI 文案以中文为主，关键识别结果支持中英同行展示。

## 8. 验收标准（MVP）

满足以下全部条件即视为 MVP 验收通过：

1. 可启动本地 Web UI，三页面可访问（Inbox/Library/Daily）。
2. 启动后自动生成标准目录结构与默认 `mappings.json`。
3. 上传或扫描 `Inbox` 音频后，系统可完成识别并归档到 `Library`。
4. 对低置信样本可在 UI 手动修正并重新落库。
5. 粘贴老师指令后，可得到结构化需求清单（按三类型分组）。
6. 生成 `Daily/YYYY-MM-DD/`，每需求条目最多复制 2 条最新 take。
7. 自动生成 `_report.txt`，准确体现覆盖率与缺遍数量。
8. 全流程有日志，能追踪失败点。

## 9. 实施建议（对应原 PRD）

- 后端建议流程函数：
  - `scan_inbox()`
  - `process_audio(file)`
  - `parse_teacher_cmd(text)`
  - `build_daily(date, needs)`
- 可先完成“规则全链路”，再接入 LLM 兜底与 UI 手工修正。

