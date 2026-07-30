# 大模型结构化抽取评测

用于比较大模型从文本中抽取结构化信息的表现。项目将模型调用、回答保存和离线评分拆成独立环节，统一检查字段内容、输出结构、原文依据、运行状态和重复运行的一致性。

## 主要功能

- 使用 JSON 定义字段名称、类型、缺失值和原文依据要求
- 使用纯文本文件管理多套提示词
- 运行 OpenAI-compatible chat completions 接口
- 运行从 stdin 接收提示、向 stdout 返回回答的命令行程序
- 导入已有回答并离线评分
- 解析普通 JSON、代码块内 JSON 和带简短前言的 JSON 对象
- 检查字段结构、状态值和原文逐字依据
- 计算字段准确率、无参考信息时的补写率、JSON 可读取率、结构通过率、耗时和输出长度
- 比较同一设置多次运行的字段一致率
- 区分调用失败、回答读取失败和模型回答质量
- 检查提示示例与测试文本的完全重复和近似重复

## 安装

```bash
git clone https://github.com/ykkai-w/Structured-Extraction-Eval.git
cd Structured-Extraction-Eval
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

项目要求 Python 3.10 及以上版本，运行代码只使用 Python 标准库。

## 快速开始

### 导入已有回答

```bash
structeval import-results \
  --input examples/import_answers.jsonl \
  --output outputs/imported

structeval evaluate \
  --dataset examples/dataset.jsonl \
  --fields examples/fields.json \
  --results outputs/imported \
  --output outputs/report
```

`summary.md` 提供汇总结果，`summary.json` 保存指标及其分母，`units.csv` 和 `fields.csv` 保存逐条记录。

### 运行命令行程序

命令行适配器将完整提示写入 stdin。进程正常结束后，stdout 内容保存为该次回答。

```json
{
  "command": ["python", "examples/mock_model.py"],
  "model": "local-demo",
  "timeout_s": 30
}
```

```bash
structeval run \
  --dataset examples/dataset.jsonl \
  --prompts examples/prompts \
  --fields examples/fields.json \
  --adapter command \
  --adapter-config examples/command_config.json \
  --output outputs/command
```

任何符合 stdin 与 stdout 约定的本地程序均可通过修改 `command` 接入。

### 运行 API 模型

复制配置并填写服务地址、模型名和密钥环境变量名：

```bash
cp examples/openai_config.example.json private_config.json
export MODEL_API_KEY="..."

structeval run \
  --dataset examples/dataset.jsonl \
  --prompts examples/prompts \
  --fields examples/fields.json \
  --adapter openai \
  --adapter-config private_config.json \
  --output outputs/api
```

配置文件只保存环境变量名，密钥通过环境变量读取。

## 数据格式

测试数据使用 JSONL，每行一条：

```json
{
  "id": "S001",
  "text": "待抽取的原始文本",
  "reference": {
    "subject": "示例主体",
    "amount": 1200,
    "technologies": ["机器视觉"]
  }
}
```

`reference` 需要包含字段规范中的全部字段。原文未提及的字段使用 `not_stated`。

模型回答采用以下结构：

```json
{
  "fields": {
    "subject": {
      "value": "示例主体",
      "status": "stated",
      "evidence": ["示例主体"]
    },
    "amount": {
      "value": "not_stated",
      "status": "not_stated",
      "evidence": []
    }
  }
}
```

状态为 `stated` 时，`evidence` 保存原文中的连续片段；状态为 `not_stated` 时，字段值使用 `not_stated`，依据使用空数组。

## 运行规则

网络中断、超时和非成功 HTTP 状态可以按设定次数重试。模型返回回答后，程序立即保存该次结果；JSON 解析、字段结构和原文依据问题进入评分，不触发重新作答。

再次运行相同命令时，已有回答的运行单元会被跳过，未取得回答的单元继续尝试。独立复跑应使用新的输出目录，并通过 `--repeats` 记录重复次数。

## 评测结果

- **JSON 可读取率**：回答能否解析为非空 JSON 对象
- **字段结构通过率**：字段及 `value`、`status`、`evidence` 是否符合规范
- **原文依据通过率**：`evidence` 是否逐字出现在输入文本中
- **可读取回答的字段准确率**：可解析回答中的字段匹配结果
- **端到端字段准确率**：将不可解析回答对应的字段计为错误
- **无参考信息时的补写率**：参考值为空时仍输出具体值的比例
- **重复运行字段一致率**：相同设置多次运行的字段值一致程度

各项指标使用不同分母。完整定义见 [docs/metrics.md](docs/metrics.md)。

## 重复文本检查

```bash
structeval scan-overlap \
  --examples examples/example_snippets.jsonl \
  --tests examples/dataset.jsonl \
  --threshold 0.92 \
  --output outputs/overlap.json
```

结果区分完全相同文本和近似文本。近似结果需要结合原文判断。

## 适用场景

字段定义明确、参考答案可复核的文本抽取任务均可使用这套流程，例如：

- 上市公司公告与年度报告
- 合同、招投标文件和制度文件
- 新闻与研究摘要
- 招聘信息与岗位说明
- 客服记录和业务工单

## 当前实现

- 字符串使用规范化后的精确匹配
- 字符串数组忽略顺序并去重
- 原文依据检查验证引文是否存在，不判断引文能否支持进一步推断
- OpenAI-compatible 适配器记录服务返回的 token 用量
- 命令行适配器要求 stdout 只输出最终回答

## 开发

```bash
python -m unittest discover -s tests -v
```

实现说明见 [docs/design.md](docs/design.md)，指标定义见 [docs/metrics.md](docs/metrics.md)，数据处理建议见 [docs/data-and-privacy.md](docs/data-and-privacy.md)。

## 许可证

[MIT](LICENSE)
