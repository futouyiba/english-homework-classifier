# Homework Audio Agent – Codx 开发包（v0.1）

> 目标：把一堆音频（孩子朗读）自动归档到「素材库」，并按老师当天微信群指令生成「每日文件夹」与缺遍报告。  
> 场景特点：口播关键词会出现但顺序可能颠倒；每条音频只对应一个条目的一遍；同一条目可能有 2~4 遍，素材库全保留；每日只拷贝/选取 2 遍到当天文件夹。

---

## 0. 给 Codx 的一句话任务

请实现一个本地 Web UI + 后端流水线：
1) 接收音频（上传或监控 Inbox 目录）；
2) 语音转写（可配置：本地 whisper 或云端 API）；
3) 从转写中抽取结构化标签（类型/编号/标题/置信度）；
4) 自动归档到素材库目录（Library）；
5) 粘贴老师指令后解析出当日需求；
6) 从素材库选择每条目 2 个 take 复制到 Daily/YYYY-MM-DD/；
7) 生成覆盖率/缺遍报告。

---

## 1. 目录结构（必须按此创建）

在项目根目录下创建：

```
HomeworkVault/
  Inbox/                 # 新音频进入（可由网盘同步/手动丢文件/网页上传落盘）
  Library/               # 长期素材库（全量保留）
    Vocab/               # 词汇（17 类）
    Sentences/           # 句子/句型（15 类）
    FastStory/           # 快嘴小孩（6 篇）
  Daily/                 # 每日打包输出
  Config/
    mappings.json        # 标题/同义词/编号映射
    teacher_cmd.txt      # 今日老师指令（从微信群复制粘贴）
  Reports/               # 历史报告（可选）

app/                     # 代码
  backend/
  frontend/
```

### 1.1 Library 的子目录命名规范

- 词汇：`Library/Vocab/C07_颜色(Color)/`
- 句子：`Library/Sentences/S05_数量相关(Quantity)/`
- 快嘴：`Library/FastStory/P03_A_super_player/`

> 注意：括号里的英文可以为空，但建议保留。

### 1.2 take 文件命名规范

- 素材库内 take：使用时间戳避免重名
  - `take_YYYYMMDD_HHMMSS.m4a`
- 每日文件夹内：固定更便于微信拖拽
  - `词汇_C07_颜色_take1.m4a`
  - `词汇_C07_颜色_take2.m4a`

---

## 2. 数据模型（后端内部）

### 2.1 枚举

- Type：`VOCAB | SENTENCE | FASTSTORY`

### 2.2 结构体

```json
{
  "id": "uuid-or-hash",
  "src_path": "HomeworkVault/Inbox/xxx.m4a",
  "duration_sec": 45.2,
  "asr": {
    "engine": "whisper_local|api",
    "text": "...转写文本...",
    "lang": "zh",
    "segments": [{"t0":0.0,"t1":5.2,"text":"..."}]
  },
  "tag": {
    "type": "VOCAB",
    "index": 7,
    "title_zh": "颜色",
    "title_en": "Color",
    "confidence": 0.86,
    "signals": {
      "hit_keywords": ["第七类","颜色"],
      "raw_number_forms": ["七"],
      "raw_title_forms": ["颜色","color"]
    }
  },
  "library_path": "HomeworkVault/Library/Vocab/C07_颜色(Color)/take_20260208_153012.m4a"
}
```

---

## 3. 核心逻辑设计（规则优先 + LLM 兜底）

### 3.1 ASR（语音转写）

- 优先只取“开头 N 秒”文本用于打标签：建议 N=20 秒（可配置），降低成本。
- 输出：完整 text + 可选 segments。

> 可接受上云；但仍提供本地 whisper 作为替换（配置开关）。

### 3.2 标签抽取：两阶段

#### 阶段 A：规则抽取（快、可解释）

输入：`asr.text`（或前 20 秒）。输出：候选 tag + 置信度。

规则要点：
1) **类型识别**（关键词命中，不要求顺序）
   - VOCAB：`词汇|单词|词组|第[一二三四五六七八九十\d]+类|大类`
   - SENTENCE：`句子|句型|句型积累|第[一二三四五六七八九十\d]+类|相关`
   - FASTSTORY：`快嘴|阅读|小短文|第[一二三四五六七八九十\d]+篇|篇`
2) **编号识别**：支持中文数字与阿拉伯数字
   - `第X类` / `X类` / `第X篇` / `X篇` / `句子X`（X=1..17/15/6）
3) **标题识别**：用 `mappings.json` 的 title/synonyms 做模糊命中
   - 词汇 17 类标题；句子 15 类标题；快嘴 6 篇标题（中英都可）
4) **编号/标题互推**：
   - 命中标题但没编号：用映射表推出 index
   - 命中编号但没标题：用映射表补齐标题

置信度建议：
- 同时命中「类型+编号」：0.85 起
- 命中「类型+标题」并能推出编号：0.75 起
- 只有类型：<=0.4

#### 阶段 B：LLM 兜底（只在低置信时调用）

触发条件：`confidence < 0.75` 或冲突（比如命中两个不同编号）。

做法：把“合法候选集合”塞给模型，强约束输出，避免瞎编。

**LLM 输入模板（发给 Codx 直接用）**

- System（固定）：
  - 你是一个作业音频分类器，只能在给定候选集合中选择。
  - 只输出 JSON，不要解释。

- User（动态）：
  - 转写文本（前 20 秒）
  - 候选集合：
    - `VOCAB: 1..17 + titles`
    - `SENTENCE: 1..15 + titles`
    - `FASTSTORY: 1..6 + titles`
  - 规则抽取得到的线索（可为空）

**LLM 输出 JSON schema：**

```json
{
  "type": "VOCAB|SENTENCE|FASTSTORY",
  "index": 1,
  "title_zh": "",
  "title_en": "",
  "confidence": 0.0,
  "notes": ""
}
```

> `notes` 仅用于调试，UI 不展示。

---

## 4. 老师指令解析（微信群自然语言）

### 4.1 需求

- 输入：一段中文自然语言，可能含括号、顿号、空格、混合数字。
- 输出：当日需求清单（按类型分别列出 index 列表；必要时保留标题）。

### 4.2 解析策略（可实现的“容错版”）

1) 先粗分块：按出现的类型关键词切分（句子/词汇/快嘴）
2) 在每块里提取：
   - 编号：`第X类/第X篇/X类/X篇/句子X/词汇X`
   - 标题：从 `mappings.json` 的 synonyms 里做命中（如“颜色相关”）
   - 括号内容：视为“同一类型的追加项目”再跑一次提取
3) 去重、排序、输出。

输出格式示例：

```json
{
  "date": "2026-02-08",
  "needs": {
    "SENTENCE": [5,8],
    "VOCAB": [7,11],
    "FASTSTORY": [3]
  }
}
```

> 说明：你已确认“句子五”=句子第5类（类=段）。

---

## 5. 每日打包策略（只取 2 条，其余留库）

对每个需求条目（type+index）：
1) 在 Library 对应目录找到所有 take
2) 默认选择“最新两条”（按文件名时间戳排序）
3) 复制到 `Daily/YYYY-MM-DD/<中文类型>/`
4) 生成 `_report.txt`

### 5.1 报告模板

```
日期：2026-02-08
老师指令：<原文>

需求清单：
- 句子：S05 数量相关；S08 颜色相关
- 词汇：C07 颜色；C11 食物
- 快嘴：P03 A super player

覆盖率：
- 句子 S05：可用 3 条，已打包 2 条 ✅
- 句子 S08：可用 1 条，仅打包 1 条 ⚠️ 缺 1 条
- 词汇 C07：可用 2 条，已打包 2 条 ✅
- 词汇 C11：可用 0 条 ❌ 缺 2 条
- 快嘴 P03：可用 4 条，已打包 2 条 ✅（其余留素材库）
```

---

## 6. mappings.json（你需要先创建的配置文件）

请在 `HomeworkVault/Config/mappings.json` 创建如下结构（Codx 负责填充默认值；你后续可改）：

```json
{
  "VOCAB": {
    "max_index": 17,
    "items": {
      "7": {"title_zh": "颜色", "title_en": "Color", "synonyms": ["颜色", "color", "第七类", "7类", "七类"]}
    }
  },
  "SENTENCE": {
    "max_index": 15,
    "items": {
      "5": {"title_zh": "数量相关", "title_en": "Quantity", "synonyms": ["数量", "数量相关", "第5类", "五类", "句子五"]}
    }
  },
  "FASTSTORY": {
    "max_index": 6,
    "items": {
      "3": {"title_zh": "A super player", "title_en": "A super player", "synonyms": ["第三篇", "第3篇", "3篇", "A super player", "super player"]}
    }
  },
  "GLOBAL_SYNONYMS": {
    "VOCAB": ["词汇", "单词", "词组"],
    "SENTENCE": ["句子", "句型", "句型积累"],
    "FASTSTORY": ["快嘴", "快嘴小孩", "快嘴少年", "阅读", "小短文"]
  }
}
```

> Codx 需要把 17/15/6 全量填充为默认映射（后续可手工微调 synonyms）。

---

## 7. Web UI（中文 + 中英同行）需求说明

### 7.1 页面：收件箱（Inbox）
- 上传音频（多选）
- 列表展示：文件名、时长、识别结果（中文 + 英文同行）、置信度、落库路径
- 对低置信项：提供下拉框手动改 type/index/title

### 7.2 页面：素材库（Library）
- 三个 Tab：词汇/句子/快嘴
- 每个条目卡片：
  - 编号 + 中文标题（英文同行）
  - take 数量
  - 最新时间
  - 展开可播放（可选）

### 7.3 页面：每日打包（Daily）
- 输入：粘贴老师指令（原文保留）
- 按钮：解析 → 展示需求清单
- 按钮：生成今日文件夹
- 展示：打包结果 + 报告内容 + 打开文件夹链接（本机）

---

## 8. 给 Codx 的实现约束与建议

- 语言：后端 Python（FastAPI）或 Node（任选其一，但要包含本地文件操作与队列处理）。
- 前端：轻量即可（React/Vue/纯 HTML 都行），要求中文 UI 文案。
- 处理流程建议：
  - `scan_inbox()` 找新文件 → 入队
  - `process_audio(file)` → ASR → tag → move_to_library
  - `parse_teacher_cmd(text)` → needs
  - `build_daily(date, needs)` → copy 2 takes → report
- 必须有：日志（用于排查识别错误）。

---

## 9. 交付物清单（MVP）

1) 可运行的 Web UI（本地）
2) 完整目录结构自动创建
3) `mappings.json` 默认全量生成
4) Inbox 上传/扫描 + 自动归档
5) 老师指令解析 + 生成 Daily 文件夹 + 报告

---

## 10. Codx 可以直接复制使用的两个 Prompt

### 10.1 音频标签兜底分类 Prompt

**System：**
你是一个作业音频标签分类器。你只能在用户给定的候选集合中选择答案。只输出 JSON，不要任何额外文本。

**User：**
转写文本（可能有口误、家长提示、顺序颠倒）：
"""
{{ASR_TEXT}}
"""

规则抽取得到的线索（可能为空）：
{{RULE_SIGNALS_JSON}}

合法候选集合（只能从中选）：
{{CANDIDATES_JSON}}

请输出：
```json
{ "type": "VOCAB|SENTENCE|FASTSTORY", "index": 1, "title_zh": "", "title_en": "", "confidence": 0.0, "notes": "" }
```

### 10.2 老师指令解析 Prompt（可选兜底）

**System：**
你是一个中文作业指令解析器。你只能输出 JSON，不要解释。

**User：**
老师指令原文：
"""
{{TEACHER_CMD}}
"""

请把指令解析为：
```json
{ "needs": { "SENTENCE": [], "VOCAB": [], "FASTSTORY": [] } }
```

约束：
- 句子是 1..15 类；词汇是 1..17 类；快嘴是 1..6 篇。
- 指令中“句子五”表示句子第5类。

---

## 11. 下一步你需要做什么（最短路径）

1) 把上述目录结构在电脑上建好（或让 Codx 代码启动时自动建）
2) 把 `mappings.json` 放到 `HomeworkVault/Config/`
3) 先随便丢 3~5 条音频到 Inbox 进行端到端测试
4) 从微信群复制一条老师指令粘贴到 WebUI，生成 Daily

---

> 如果你希望我把本文件拆成多份（例如 README.md / ARCH.md / PROMPTS.md / CONFIG.md），你告诉我“按文件拆分”，我会把它们分别拆到多个 canvas 文档里，便于你直接下载成多文件。

