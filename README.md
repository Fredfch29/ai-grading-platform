# AI 阅卷平台

基于大语言模型的智能阅卷评估平台，支持上传 Excel 答卷 → AI 自动评分 → 可视化 Dashboard → 人工复核 → 导出报告。

## 快速开始

### 环境要求

- Python 3.10+
- 大模型 API Key（支持所有 OpenAI 兼容接口，如 DeepSeek、OpenAI、智谱等）

### PyCharm 打开即用（推荐，适合新手）

> ⚠️ GitHub ZIP 下载解压后会多一层外壳文件夹，如 `ai-grading-platform-main/`，这是正常的。**PyCharm 打开这层外壳即可**，里面的 `.idea/` 是 PyCharm 自动生成的配置文件，不用管它（删了也不影响）。

1. **下载解压**：从 GitHub 下载 ZIP，解压得到 `ai-grading-platform-main/`
2. **PyCharm 打开**：PyCharm → File → Open → 选择 `ai-grading-platform-main` 文件夹
3. **创建虚拟环境**：右下角提示 "No interpreter" → Add New Interpreter → Python 3.10+ → OK
4. **安装依赖**：顶部黄色横幅 "Package requirements are not satisfied" → **Install requirements**（或打开 `ai_grading_platform/requirements.txt`，点蓝色 Install 链接）⏳ 等 1-2 分钟
5. **运行**：左侧项目树打开 `ai_grading_platform/` → 右键 `streamlit_app.py` → **Run 'streamlit_app'**
6. 底部 Run 窗口显示 `Local URL: http://localhost:8501`，点它打开浏览器
7. **填写 API Key**：左侧边栏填入你的 API Key、Base URL、Model → 上传 Excel → 点「开始评分」

> 如果 PyCharm 没弹出安装依赖的提示，可以在底部 Terminal 标签页手动输入：
> ```bash
> pip install -r ai_grading_platform/requirements.txt
> ```

### 终端安装运行（老手）

```bash
git clone https://github.com/Fredfch29/ai-grading-platform.git
cd ai-grading-platform/ai_grading_platform
pip install -r requirements.txt
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

如果换了全新的题库，可以将题目文本发给 AI 自动生成新的 `config.json`，Prompt 如下：

````markdown
# Role
你是一个专业、严谨的 AI 考试系统数据配置专家。你的任务是将用户提供的"非结构化笔试题库文本"提取、清洗并转换为严格符合预设格式的 JSON 配置文件。

# Objective
读取用户提供的笔试题目、阅读材料、参考答案和打分要求，将其转换为供 AI 自动阅卷系统使用的 `config.json` 格式。

# Rule & Field Mapping
必须严格输出一个 JSON 对象，包含一个 "questions" 数组。数组中的每个元素代表一道题，且必须包含以下 7 个字段：

1. "q_num" (字符串): 题目原始编号，例如 "Q1", "Q13"。这是与外部问卷系统导出表格（Excel）进行前缀匹配的核心锚点，请务必精准提取纯题号。
2. "id" (字符串): 题目的简短描述性名称（不含题号），用于系统日志打印，例如 "潮玩盲盒翻译"、"评估AI邮件问题"。
3. "keyword" (字符串): 4-8个字的核心考点简写，用于最终在成绩报表中高亮显示，例如 "英文邮件打分"、"大模型幻觉"、"代码查错"。
4. "max_score" (整数): 该题的满分分值。请从文本中提取数值（如"本题10分"提取为 10）。
5. "background" (字符串, 必填): 如果该题有依赖的阅读材料、长题干、测试数据、前置背景设定等，请完整提取到这里。如果没有前置材料，请严格填入 ""（空字符串）。
6. "reference_answer" (字符串, 必填): 如果原文提供了"参考答案"或"标准答案"，请提取到这里。如果没有，请严格填入 ""（空字符串）。
7. "rubric" (字符串, 必填): 详细的打分标准。请将文本中的评分细则（如得分点、扣分项、分档评分等）整理成一段通顺、结构化、指令清晰的文本，作为后续 AI 阅卷大模型的系统级评判依据。

# Constraints
1. 绝对不要捏造用户没有提供的题目内容，严格忠于原文本。
2. JSON 格式必须绝对合法（注意正确转义双引号 `\"`、换行符必须使用 `\n`）。
3. 你的输出只能是 JSON 代码，不需要任何解释性的废话，请务必使用 ```json 和 ``` 包裹。

# Input Data
【请在此处粘贴你的TXT题库内容】
````

将「【请在此处粘贴你的TXT题库内容】」替换为实际题目文本，发给 ChatGPT / Claude / DeepSeek 等大模型，用生成的 JSON 替换 `config.json` 即可。

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
