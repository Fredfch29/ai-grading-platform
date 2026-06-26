# AI 阅卷平台

基于大语言模型的智能阅卷评估平台，支持上传 Excel 答卷 → AI 自动评分 → 可视化 Dashboard → 人工复核 → 导出报告。

## 快速开始

### 环境要求

- Python 3.10+
- 大模型 API Key（支持所有 OpenAI 兼容接口，如 DeepSeek、OpenAI、智谱等）

### 安装运行

```bash
# 1. 克隆仓库
git clone https://github.com/Fredfch29/ai-grading-platform.git
cd ai-grading-platform/ai_grading_platform

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
streamlit run streamlit_app.py
```

浏览器会自动打开 `http://localhost:8501`。

### 配置 API（三选一）

**方式 A：侧边栏填写（推荐）**

启动后在左侧边栏填入你的 API Key、Base URL 和 Model，然后上传 Excel 开始评分。
每人用自己的 API，互不影响。

**方式 B：创建 `.env` 文件**

在 `ai_grading_platform/` 目录下创建 `.env`：

```env
AI_GRADER_API_KEY=sk-你的密钥
AI_GRADER_BASE_URL=https://api.deepseek.com
AI_GRADER_MODEL=deepseek-v4-pro
```

**方式 C：环境变量**

```bash
export AI_GRADER_API_KEY="sk-你的密钥"
export AI_GRADER_BASE_URL="https://api.deepseek.com"
export AI_GRADER_MODEL="deepseek-v4-pro"
```

> **注意**：侧边栏填写的配置优先级最高，会在点击"开始评分"时覆盖 `.env` 和环境变量的值。

## 功能流程

| 步骤 | 功能 | 说明 |
|------|------|------|
| 1. 上传 | 上传 Excel 答卷 | 支持通过列名前缀自动匹配（`Q1_`→姓名、`Q4_`→学校、`Q13_`-`Q27_`→作答） |
| 2. 评分 | AI 批量评分 | 逐题调用大模型评分，支持**暂停/继续/停止**，断点续评（刷新不丢进度） |
| 3. Dashboard | 可视化分析 | 总分排名表、成绩分布折线图、能力维度雷达图、候选人详情 |
| 4. 复核 | 人工复核 | 查看 AI 评分理由，手动修改分数，撤销修改 |
| 5. 导出 | 下载报告 | 导出 Excel 成绩单 + HTML 可视化报告，复核修改自动标记 `【人工修改】` |

## Excel 数据格式要求

上传的 Excel 需要包含以下列（列名支持前缀匹配）：

| 前缀 | 内容 | 示例列名 |
|------|------|----------|
| `Q1_` | 候选人姓名 | `Q1_姓名` |
| `Q4_` | 学校/单位 | `Q4_学校` |
| `Q13_` ~ `Q27_` | 各题作答 | `Q13_连读标注` ... `Q27_系统指令` |

## 评分标准

`config.json` 中预置了 15 道题的评分标准（Q13-Q27），涵盖：

- 语音连读标注
- 英语语法分析（长难句、倒装句）
- 中译英翻译（潮玩、网络用语、医学文本）
- 英译中翻译（电竞、社媒、旅游导览）
- 翻译质量评估（文言文、医学）
- AI 术语简述（幻觉、提示词注入）
- AI 评测分析与系统指令撰写

如需修改题型或评分标准，编辑 `config.json` 即可。

## 项目结构

```
ai_grading_platform/
├── streamlit_app.py    # Streamlit Web 应用（主文件）
├── ai_grader.py        # AI 评分核心（调用大模型）
├── config.json         # 题目评分标准配置
├── excel_parser.py     # Excel 解析工具
├── html_report.py      # HTML 报告生成
├── main.py             # CLI 入口（命令行批量评分）
└── requirements.txt    # Python 依赖
```

## 命令行使用（可选）

如果不想用 Streamlit UI，也可以直接在终端批量评分：

```bash
cp ai_grading_platform/.env.example ai_grading_platform/.env  # 配置 API Key
cd ai_grading_platform
python main.py
```

## License

MIT
