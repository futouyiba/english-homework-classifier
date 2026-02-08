# Homework Audio Agent

本项目用于把孩子朗读音频自动归档到素材库，并依据老师当天指令生成每日打包文件与缺遍报告。

## 文档导航

- 需求总览：`homework_audio_agent_requirements.md`
- 架构设计：`ARCH.md`
- 接口定义：`API.md`
- 配置规范：`CONFIG.md`
- LLM Prompt：`PROMPTS.md`
- 测试与验收：`TEST_PLAN.md`
- 原始 PRD：`homework_audio_agent_codx_prd.md`

## 快速启动（后端骨架）

1. 安装依赖：
```bash
pip install -r app/backend/requirements.txt
```
2. 启动服务：
```bash
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000 --reload
```
3. 打开接口文档：`http://127.0.0.1:8000/docs`
4. 打开联调页面：`http://127.0.0.1:8000/ui`

### ASR 环境变量

- `ASR_ENGINE`: `whisper_local`（默认）| `openai_api` | `stub`
- `ASR_PROCESS_SCOPE`: `hybrid`（默认）| `head` | `full`
  - `hybrid`: 全量转写 + 头部截断优化标签文本
  - `head`: 仅头部转写（失败会回退全量）
  - `full`: 全量转写（标签文本从分段截取）
- `ASR_TAG_WINDOW_SEC`: 标签抽取使用的前 N 秒文本（默认 `20`）
- `WHISPER_MODEL`: 本地 Whisper 模型（默认 `small`）
- `WHISPER_LANGUAGE`: Whisper 语言（默认 `zh`）
- `OPENAI_API_KEY`: 当 `ASR_ENGINE=openai_api` 时必填
- `OPENAI_ASR_MODEL`: OpenAI 转写模型（默认 `whisper-1`）
- `OPENAI_BASE_URL`: 可选，自定义 OpenAI 兼容网关

本地 Whisper 依赖系统 `ffmpeg`，请先确保命令行可用。

调试建议：
- 先用 `POST /api/asr/test` 验证转写与标签预览，再跑完整归档流程。
- `scope=head` 可测试“仅前 N 秒转写”效果；`scope=full` 可测试全量转写；`scope=hybrid` 对齐主流程默认策略。

### 原文转换与分拣

当 `originalText/` 下放入 `pdf + docx` 原文后，可运行：
```bash
python scripts/prepare_original_text.py
```
该脚本会自动完成：
- 转换：生成 `originalText/converted/*.txt`
- 分拣：生成 `originalText/structured/vocab_17.json` / `sentence_15.json` / `faststory_6.json`
- 配置：刷新 `HomeworkVault/Config/mappings.json`

## MVP 目标

- 本地 Web UI（Inbox / Library / Daily）。
- 音频接收、转写、标签识别、自动归档。
- 老师指令解析为结构化需求。
- 每条需求最多打包 2 条 take。
- 自动生成覆盖率/缺遍报告。

## 核心流程

1. 上传或扫描音频进入 `HomeworkVault/Inbox/`。
2. 执行 ASR（本地 Whisper 或云 API）得到转写文本。
3. 规则抽取标签（type/index/title/confidence），低置信时 LLM 兜底。
4. 归档到 `HomeworkVault/Library/` 对应目录。
5. 粘贴老师指令并解析当日需求。
6. 生成 `HomeworkVault/Daily/YYYY-MM-DD/` 与 `_report.txt`。

## 目录结构

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

## 业务约束

- 每条音频对应一个条目的一遍。
- 同一条目素材库保留全部 take（常见 2~4 遍）。
- Daily 打包每条目只选 2 遍（默认最新两条）。
- 指令与口播可能有顺序颠倒、口误、混合数字，解析需容错。
