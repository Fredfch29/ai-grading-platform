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
5. **运行**：点 PyCharm 底部的 **Terminal** 标签页，输入以下命令**（⚠️ 注意：不能用右上角的 ▶️ 运行按钮，必须用终端命令）**：

   ```bash
   cd ai_grading_platform
   streamlit run streamlit_app.py
   ```

6. 终端显示 `Local URL: http://localhost:8501` → 按住 Cmd 点链接（Windows 按 Ctrl）打开浏览器
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
| 1. 上传 | 上传 Excel 答卷 | 自动识别 Q+数字列名，与 config.json 题号匹配，侧边栏可自定义学生信息列前缀 |
| 2. 评分 | AI 批量评分 | 逐题调用大模型评分，支持**暂停/继续/停止**，断点续评（刷新不丢进度） |
| 3. Dashboard | 可视化分析 | 总分排名表、成绩分布折线图、能力维度雷达图、候选人详情 |
| 4. 复核 | 人工复核 | 查看 AI 评分理由，手动修改分数，撤销修改 |
| 5. 导出 | 下载报告 | 导出 Excel 成绩单 + HTML 可视化报告，复核修改自动标记 `【人工修改】` |

## Excel 数据格式要求

### 学生信息列（固定用途）

`Q1_` 和 `Q4_` 是**学生信息专用列前缀**，与题目编号无关：

| 列前缀 | 用途 | 示例列名 | 可否修改 |
|--------|------|----------|----------|
| `Q1_` | 候选人姓名 | `Q1_姓名`、`Q1_text` | 可在侧边栏「Excel 列名映射」自定义 |
| `Q4_` | 学校/单位 | `Q4_学校`、`Q4_text` | 可在侧边栏「Excel 列名映射」自定义 |

> 如果你的问卷系统导出列名是 `A1_`、`B4_` 等不同格式，启动后在侧边栏 **📋 Excel 列名映射** 里改成对应前缀即可，不需要改代码。

### 题目列（与 config.json 对齐）

题目列的编号**不要求从 Q13 开始**，只要 Excel 列名前缀和 `config.json` 中的 `q_num` **一一对应**即可。

系统自动识别所有 `Q + 数字` 格式的列 → 取编号 → 与 `config.json` 的 `q_num` 做匹配。

**举例**：

```
config.json 配置:
  { "q_num": "Q5",  "keyword": "翻译题" }
  { "q_num": "Q7",  "keyword": "作文题" }
  { "q_num": "Q12", "keyword": "听力题" }

Excel 列名:
  Q5_中译英    ← 匹配 Q5 ✅
  Q7_大作文    ← 匹配 Q7 ✅
  Q12_听力填空 ← 匹配 Q12 ✅
```

编号可以跳（5→7→12），不要求连续，不要求从某个特定数字开始。

## 评分标准

仓库内置 `config.json` 为**示例题库**（3 道样题），仅用于演示格式。实际使用时，在侧边栏选择 **"📤 上传配置文件"** 导入你自己的题库。

| 方式 | 适用场景 |
|------|----------|
| 📦 内置配置 | 快速体验、格式参考 |
| 📤 上传配置 | 真实阅卷，每题一套私有 `config.json` |

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

## 自定义与二次开发指南

如果你要针对自己的题库改造这个项目，以下是各文件的职责和改造入口速查。

### config.json 字段说明

| 字段 | 作用 | 必填 | 可删/可加 |
|------|------|------|-----------|
| `q_num` | Excel 列名前缀匹配，如 `Q13` 匹配列 `Q13_连读标注` | ✅ 必填 | 删了系统找不到考生答案 |
| `keyword` | 结果字典 Key（`{keyword}_得分`），Dashboard/导出/复核都靠它定位 | ✅ 必填 | 删了整个结果体系崩溃 |
| `max_score` | 满分值，AI 评分上限校验 | ✅ 必填 | 删了分数校验失效 |
| `rubric` | 发给 AI 的打分依据 | ✅ 必填 | 删了 AI 不知道按什么标准评分 |
| `id` | 系统日志 + `COMPETENCY_LABEL_MAP` 能力维度分组 | 可选 | 删了该题归类到「其他能力」，不影响评分 |
| `background` | 拼入 AI Prompt，用于阅读材料/长题干 | 可选 | 可删（留空字符串），可加 |
| `reference_answer` | 拼入 AI Prompt，作为参考答案辅助判断 | 可选 | 可删（留空字符串），可加 |
| *自定义字段* | 不与现有字段重名即可自由添加，代码自动忽略 | — | 加了不影响，要用需改代码 |

### 各文件改造入口

| 需求 | 改哪个文件 | 改哪里 |
|------|-----------|--------|
| 换题库（不改题型结构） | 不需要改代码 | 上传新的 `config.json` 即可 |
| 调整 AI 评分逻辑 / Prompt | [ai_grader.py](ai_grading_platform/ai_grader.py) | `grade_single_question()` 函数中的 `prompt` 字符串（第 73-91 行） |
| 调整能力维度分类 | [streamlit_app.py](ai_grading_platform/streamlit_app.py) | `COMPETENCY_LABEL_MAP` 字典（第 62 行），key 匹配 `config.json` 的 `id` 字段 |
| 修改 Dashboard 图表/排名 | [streamlit_app.py](ai_grading_platform/streamlit_app.py) | `compute_question_stats()`、`build_ranking_df()`、`build_score_line_chart()`、`build_radar_chart()` |
| 修改 Excel 导出列 | [streamlit_app.py](ai_grading_platform/streamlit_app.py) | `_generate_download_files()` 中的列顺序和列名 |
| 修改 HTML 报告样式/结构 | [html_report.py](ai_grading_platform/html_report.py) | `generate_html_report()` |
| 修改 Excel 列名匹配规则 | [streamlit_app.py](ai_grading_platform/streamlit_app.py) | `parse_candidates()` 中的列前缀匹配（第 129、131、144 行） |
| 修改 Streamlit 页面 UI | [streamlit_app.py](ai_grading_platform/streamlit_app.py) | 各 `render_*` 函数 |
| 新增 `config.json` 字段并让 AI 评分用到 | [ai_grader.py](ai_grading_platform/ai_grader.py) | 在 `grade_single_question()` 中读取 config 里的新字段，拼入 `prompt` |

### 数据流转全景

```
Excel 上传
  │
  ├─► parse_candidates()         ── Q1_→姓名, Q4_→学校, Q13_~Q27_→作答
  │
  ├─► _grade_one_candidate()     ── 逐题调用 ai_grader.grade_single_question()
  │      │
  │      └─► ai_grader.py        ── 构建 Prompt → 调用大模型 → 返回 (分数, 理由)
  │
  ├─► grading_results[]          ── [{姓名, 学校, 总分, {keyword}_得分, {keyword}_评价, ...}]
  │      │
  │      ├─► Dashboard           ── 排名表 / 折线图 / 雷达图 / 能力维度
  │      ├─► 人工复核             ── st.session_state.reviewed_scores → 覆盖分数
  │      └─► 下载                 ── Excel (_generate_download_files) + HTML (html_report.py)
  │
  └─► config.json                ── 贯穿全程：标题/题目列表/满分/评分标准
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
