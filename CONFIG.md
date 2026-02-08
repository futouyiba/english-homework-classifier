# 配置规范

## 1. 配置文件位置

- 主配置：`HomeworkVault/Config/mappings.json`
- 指令输入缓存：`HomeworkVault/Config/teacher_cmd.txt`

## 2. mappings.json 结构

```json
{
  "VOCAB": {
    "max_index": 17,
    "items": {
      "7": {
        "title_zh": "颜色",
        "title_en": "Color",
        "synonyms": ["颜色", "color", "第七类", "7类", "七类"]
      }
    }
  },
  "SENTENCE": {
    "max_index": 15,
    "items": {
      "5": {
        "title_zh": "数量相关",
        "title_en": "Quantity",
        "synonyms": ["数量", "数量相关", "第5类", "五类", "句子五"]
      }
    }
  },
  "FASTSTORY": {
    "max_index": 6,
    "items": {
      "3": {
        "title_zh": "A super player",
        "title_en": "A super player",
        "synonyms": ["第三篇", "第3篇", "3篇", "A super player", "super player"]
      }
    }
  },
  "GLOBAL_SYNONYMS": {
    "VOCAB": ["词汇", "单词", "词组"],
    "SENTENCE": ["句子", "句型", "句型积累"],
    "FASTSTORY": ["快嘴", "快嘴小孩", "快嘴少年", "阅读", "小短文"]
  }
}
```

## 3. 初始化规则

- 启动时若 `mappings.json` 不存在，自动生成默认文件。
- 必须全量生成：
  - `VOCAB`: 1..17
  - `SENTENCE`: 1..15
  - `FASTSTORY`: 1..6
- 默认 `title_zh/title_en` 可先给占位值，后续人工微调。

## 4. 配置校验规则

- `max_index` 必须与条目上限一致。
- `items` 的 key 必须在合法范围内。
- `synonyms` 建议包含：
  - 中文标题
  - 英文标题（如有）
  - 数字口播变体（如“第七类”“7类”“七类”）

## 5. 与识别逻辑的关系

- 类型识别优先使用 `GLOBAL_SYNONYMS`。
- 标题识别与编号互推使用 `items[index]`。
- 老师指令解析与音频标签识别共用同一份 `mappings.json`。

## 6. 变更建议

- 每次修改 `mappings.json` 后，建议用 3~5 条样本做回归测试。
- 优先补充高频误识别词到 `synonyms`，再考虑调整规则或 LLM 兜底阈值。

