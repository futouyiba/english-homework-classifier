# LLM Prompt 模板

## 1. 音频标签兜底分类

适用场景：
- 规则抽取 `confidence < 0.75`
- 或规则抽取出现冲突（如多个编号）

System:

```text
你是一个作业音频标签分类器。你只能在用户给定的候选集合中选择答案。只输出 JSON，不要任何额外文本。
```

User:

```text
转写文本（可能有口误、家长提示、顺序颠倒）：
"""
{{ASR_TEXT}}
"""

规则抽取得到的线索（可能为空）：
{{RULE_SIGNALS_JSON}}

合法候选集合（只能从中选）：
{{CANDIDATES_JSON}}

请输出：
{ "type": "VOCAB|SENTENCE|FASTSTORY", "index": 1, "title_zh": "", "title_en": "", "confidence": 0.0, "notes": "" }
```

输出要求：
- 仅 JSON
- `index` 必须落在候选合法范围
- `notes` 仅用于调试，不在 UI 展示

## 2. 老师指令解析（可选兜底）

适用场景：
- 规则解析失败或存在明显歧义时作为补充

System:

```text
你是一个中文作业指令解析器。你只能输出 JSON，不要解释。
```

User:

```text
老师指令原文：
"""
{{TEACHER_CMD}}
"""

请把指令解析为：
{ "needs": { "SENTENCE": [], "VOCAB": [], "FASTSTORY": [] } }

约束：
- 句子是 1..15 类；词汇是 1..17 类；快嘴是 1..6 篇。
- 指令中“句子五”表示句子第5类。
```

输出要求：
- 仅 JSON
- 去重并升序
- 不生成范围外编号

