"""
AI 阅卷平台 — Streamlit Web App (Phase 2)
==========================================
浏览器中上传 Excel → AI 实时评分 → 可视化 Dashboard → 下载报告

运行方式：
    cd ai_grading_platform
    streamlit run streamlit_app.py
"""

# ============================================================
# 1. IMPORTS + 环境注入
# ============================================================
import os
import sys
import json
import time
import importlib
import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ── 页面配置（必须是第一个 st 调用） ──
st.set_page_config(
    page_title="AI 阅卷平台",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 脚本所在目录 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 自动加载 .env 文件（与 ai_grader.py 相同逻辑） ──
_ENV_DIRS = [
    BASE_DIR,
    os.path.dirname(BASE_DIR),
    os.path.dirname(os.path.dirname(BASE_DIR)),
]
_ENV_LOADED = False
for _d in _ENV_DIRS:
    _ENV_PATH = os.path.join(_d, ".env")
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _key, _val = _line.split("=", 1)
                    os.environ.setdefault(_key.strip(), _val.strip())
        break

# ── 导入 ai_grader（延迟创建 client，无需预先配置 API Key） ──
import ai_grader


# ============================================================
# 能力维度映射（与 html_report.py 保持同步）
# ============================================================
COMPETENCY_LABEL_MAP = {
    "连读记号标注": "语音标注能力",
    "英语语法分析": "语法分析能力",
    "中译英翻译":   "中译英能力",
    "英译中翻译":   "英译中能力",
    "翻译质量评估": "翻译评估能力",
    "AI术语简述":   "AI基础认知",
    "AI评测分析":   "AI评测设计能力",
    "系统指令撰写": "AI评测设计能力",
}


# ============================================================
# 2. SESSION STATE 初始化
# ============================================================
def init_session_state():
    """确保所有 session state key 都存在默认值。"""
    defaults = {
        # API — widget keys (Streamlit manages these via st.text_input key=)
        "sidebar_api_key": os.getenv("AI_GRADER_API_KEY", ""),
        "sidebar_base_url": os.getenv("AI_GRADER_BASE_URL", "https://api.deepseek.com"),
        "sidebar_model": os.getenv("AI_GRADER_MODEL", "deepseek-v4-pro"),
        # Config
        "sidebar_config_source": "builtin",  # "builtin" | "custom"
        "config": None,                      # loaded config dict
        "config_json_str": "",               # pasted / uploaded JSON text
        "config_json_textarea": "",          # textarea key
        "config_error": "",
        # Excel
        "uploaded_file_name": "",
        "df": None,
        "parse_error": "",
        "name_col_prefix": "Q1_",         # 姓名列前缀
        "school_col_prefix": "Q4_",       # 学校列前缀
        # Grading
        "grading_status": "idle",     # "idle" | "running" | "paused" | "completed"
        "grading_results": [],
        "grading_log": [],
        "grading_queue": [],           # 待评分队列 [(name, school, answers), ...]
        # Human review
        "reviewed_scores": {},         # {name: {keyword: {original_score, new_score, reason}}}
        "candidate_answers": {},       # {name: {keyword: answer_text}}
        # Dashboard
        "selected_candidate": "",
        # Download
        "excel_bytes": None,
        "html_bytes": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ============================================================
# 3. 辅助函数
# ============================================================

def parse_candidates(df):
    """
    解析候选人 DataFrame，提取姓名、学校，以及各题答案。
    返回:
        candidates: [(name, school, {q_num: answer_text}), ...]
        question_columns: {q_num: actual_col_name}
    """
    candidates = []

    # 找出姓名和学校列（前缀可从侧边栏配置）
    name_col = None
    school_col = None
    name_prefix = st.session_state.get("name_col_prefix", "Q1_")
    school_prefix = st.session_state.get("school_col_prefix", "Q4_")
    for col in df.columns:
        col_str = str(col)
        if col_str.startswith(name_prefix):
            name_col = col
        elif col_str.startswith(school_prefix):
            school_col = col

    for idx, row in df.iterrows():
        name = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else f"候选人_{idx+1}"
        school = str(row[school_col]).strip() if school_col and pd.notna(row[school_col]) else "未知学校"

        # 提取所有以 Q 开头后跟数字的列（题目答案）
        answers = {}
        for col in df.columns:
            col_str = str(col)
            # 匹配 Q13_, Q14_ 等格式
            if col_str.startswith('Q') and len(col_str) >= 2 and col_str[1:].split('_')[0].isdigit():
                q_num = col_str.split('_')[0]  # e.g. "Q13"
                val = row[col]
                answers[q_num] = str(val).strip() if pd.notna(val) else ""

        candidates.append((name, school, answers))

    return candidates


def load_builtin_config():
    """加载内置 config.json。"""
    config_path = os.path.join(BASE_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_question_stats(results, config):
    """计算每道题的 min/max/avg 得分。"""
    questions = config["questions"]
    stats = []
    for q in questions:
        keyword = q["keyword"]
        key = f"{keyword}_得分"
        scores = [r[key] for r in results if key in r and isinstance(r[key], (int, float))]
        stats.append({
            "keyword": keyword,
            "max_possible": q["max_score"],
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "avg": round(sum(scores) / len(scores), 1) if scores else 0,
        })
    return stats


def derive_competency_groups(config):
    """根据 config 的 id 字段和 COMPETENCY_LABEL_MAP 派生能力维度分组。"""
    groups = {}
    for q in config["questions"]:
        qid = q.get("id", "")
        label = COMPETENCY_LABEL_MAP.get(qid, "其他能力")
        groups.setdefault(label, []).append((q["keyword"], q["max_score"]))
    return groups


def compute_competency_scores(results, groups):
    """为每个候选人计算各能力维度的得分率 (0-100)。"""
    comp_scores = []
    for candidate in results:
        dims = {}
        for label, items in groups.items():
            actual = sum(candidate.get(f"{kw}_得分", 0) for kw, _ in items)
            max_possible = sum(ms for _, ms in items)
            pct = round(actual / max_possible * 100, 1) if max_possible > 0 else 0
            dims[label] = pct
        comp_scores.append({
            "name": candidate["姓名"],
            "total": candidate["总分"],
            "dimensions": dims,
        })
    comp_scores.sort(key=lambda x: x["total"], reverse=True)
    return comp_scores


def build_ranking_df(results):
    """构建带排名的 DataFrame。"""
    df = pd.DataFrame(results)
    key_cols = ["姓名", "学校", "总分"]
    cols = [c for c in key_cols if c in df.columns]
    # 其他列：得分列在前，评价列在后
    score_cols = [c for c in df.columns if c.endswith("_得分")]
    reason_cols = [c for c in df.columns if c.endswith("_评价")]
    for c in score_cols + reason_cols:
        if c not in cols:
            cols.append(c)
    df = df[cols]
    df = df.sort_values("总分", ascending=False).reset_index(drop=True)
    df.index = df.index + 1  # 排名从 1 开始
    df.index.name = "排名"
    return df


# ============================================================
# 4. 图表构建（Plotly）
# ============================================================
import plotly.graph_objects as go
import plotly.express as px


def build_score_line_chart(stats):
    """构建各题得分趋势折线图（最高分/平均分/最低分）。"""
    keywords = [s["keyword"] for s in stats]
    max_scores = [s["max"] for s in stats]
    avg_scores = [s["avg"] for s in stats]
    min_scores = [s["min"] for s in stats]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=keywords, y=max_scores,
        mode="lines+markers",
        name="最高分",
        line=dict(color="#e53935", width=2.5),
        marker=dict(size=8, color="#e53935"),
        hovertemplate="%{x}<br>最高分: %{y} 分<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=keywords, y=avg_scores,
        mode="lines+markers",
        name="平均分",
        line=dict(color="#1e88e5", width=2.5),
        marker=dict(size=8, color="#1e88e5"),
        hovertemplate="%{x}<br>平均分: %{y} 分<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=keywords, y=min_scores,
        mode="lines+markers",
        name="最低分",
        line=dict(color="#43a047", width=2.5),
        marker=dict(size=8, color="#43a047"),
        hovertemplate="%{x}<br>最低分: %{y} 分<extra></extra>",
    ))

    fig.update_layout(
        xaxis=dict(
            title="题目",
            tickangle=-30,
            tickfont=dict(size=11),
        ),
        yaxis=dict(
            title="得分",
            rangemode="tozero",
            dtick=1,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        margin=dict(t=10, b=60, l=50, r=20),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig


def build_radar_chart(candidate, dim_labels):
    """为单个候选人构建能力画像雷达图。"""
    name = candidate["name"]
    values = [candidate["dimensions"].get(label, 0) for label in dim_labels]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=dim_labels,
        fill="toself",
        name=name,
        fillcolor="rgba(26,35,126,0.2)",
        line=dict(color="#1a237e", width=2),
        marker=dict(size=5, color="#1a237e"),
        hovertemplate="%{theta}: %{r}%<extra></extra>",
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[0, 20, 40, 60, 80, 100],
                tickfont=dict(size=9),
            ),
            angularaxis=dict(
                tickfont=dict(size=10),
            ),
        ),
        title=dict(
            text=f"{name}<br><span style='font-size:12px;color:#666'>总分 {candidate['total']} 分</span>",
            x=0.5,
            font=dict(size=13),
        ),
        margin=dict(t=50, b=30, l=50, r=50),
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig


# ============================================================
# 5. SIDEBAR
# ============================================================

def render_sidebar():
    """渲染左侧边栏：API 配置 + 评分配置 + 控制 + 下载。"""
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/test-partial-passed.png", width=64)
        st.title("AI 阅卷平台")

        # ── API 配置 ──
        with st.expander("⚙️ API 配置", expanded=True):
            st.text_input(
                "API Key",
                value=st.session_state.sidebar_api_key,
                type="password",
                placeholder="sk-...",
                help="DeepSeek API 密钥",
                key="sidebar_api_key",
            )

            st.text_input(
                "Base URL",
                value=st.session_state.sidebar_base_url,
                placeholder="https://api.deepseek.com",
                help="API 接口地址",
                key="sidebar_base_url",
            )

            st.text_input(
                "Model",
                value=st.session_state.sidebar_model,
                placeholder="deepseek-v4-pro",
                help="模型名称",
                key="sidebar_model",
            )

        # ── Excel 列名映射 ──
        with st.expander("📋 Excel 列名映射", expanded=False):
            st.caption(
                "**学生信息列**（固定用途，与题目无关）：\n\n"
                "这两列只用来读姓名和学校，不需要跟题目编号对齐。\n"
                "如果你的问卷系统导出的姓名列叫 `A1_` 而不是 `Q1_`，在这里改前缀就行。"
            )
            st.text_input(
                "姓名列前缀",
                value=st.session_state.name_col_prefix,
                help="用于识别姓名列的列名前缀。例如 Q1_ 可匹配 Q1_姓名、Q1_text 等",
                key="name_col_prefix",
            )
            st.text_input(
                "学校列前缀",
                value=st.session_state.school_col_prefix,
                help="用于识别学校列的列名前缀。例如 Q4_ 可匹配 Q4_学校、Q4_text 等",
                key="school_col_prefix",
            )
            st.divider()
            st.caption(
                "**题目列**（自动识别，无需配置）：\n\n"
                "系统自动扫描 Excel 中所有 `Q + 数字` 格式的列作为题目答案，"
                "然后与 `config.json` 中的 `q_num` 字段做匹配。\n\n"
                "> ⚠️ **题目编号不要求从 Q13 开始**——只要 config.json 的 `q_num` 和 Excel 列名一致即可。\n\n"
                "**示例**：\n"
                "- config 配置了 `\"q_num\": \"Q5\"`、`\"q_num\": \"Q7\"`\n"
                "- Excel 中有 `Q5_翻译`、`Q7_作文` 两列\n"
                "- 系统自动匹配：Q5 ↔ Q5_翻译，Q7 ↔ Q7_作文 ✅"
            )

        # ── 评分配置 ──
        with st.expander("📝 评分配置", expanded=True):
            st.radio(
                "选择题目配置",
                options=["builtin", "custom"],
                format_func=lambda x: "📦 内置示例" if x == "builtin" else "✏️ 自定义配置",
                horizontal=True,
                key="sidebar_config_source",
            )

            if st.session_state.sidebar_config_source == "custom":
                st.caption("将 AI 生成的 JSON 粘贴到下方，点「加载配置」即可。")
                st.text_area(
                    "配置 JSON",
                    value=st.session_state.config_json_str,
                    height=250,
                    placeholder='{\n  "questions": [\n    {\n      "q_num": "Q5",\n      "id": "翻译题",\n      "keyword": "中译英翻译",\n      "max_score": 10,\n      "background": "请将以下中文翻译成英文...",\n      "reference_answer": "",\n      "rubric": "满分10分，评分标准...",\n    }\n  ]\n}',
                    key="config_json_textarea",
                )
                col1, col2 = st.columns([1, 3])
                with col1:
                    load_clicked = st.button(
                        "🔍 加载配置",
                        use_container_width=True,
                        key="config_load_btn",
                    )
                with col2:
                    if load_clicked:
                        raw = st.session_state.config_json_textarea.strip()
                        if not raw:
                            st.session_state.config_error = "请先粘贴 JSON 内容"
                            st.error(st.session_state.config_error)
                        else:
                            try:
                                config = json.loads(raw)
                                if "questions" not in config:
                                    st.session_state.config_error = "JSON 缺少 'questions' 字段"
                                    st.error(st.session_state.config_error)
                                else:
                                    st.session_state.config = config
                                    st.session_state.config_json_str = raw
                                    st.session_state.config_error = ""
                                    st.success(f"✅ 已加载，共 {len(config.get('questions', []))} 道题")
                            except json.JSONDecodeError as e:
                                st.session_state.config_error = f"JSON 解析失败: {e}"
                                st.error(st.session_state.config_error)

                with st.expander("📤 或上传 JSON 文件", expanded=False):
                    uploaded_config = st.file_uploader(
                        "选择 .json 文件",
                        type=["json"],
                        key="sidebar_config_uploader",
                        label_visibility="collapsed",
                    )
                    if uploaded_config is not None:
                        try:
                            config_text = uploaded_config.read().decode("utf-8")
                            config = json.loads(config_text)
                            st.session_state.config = config
                            st.session_state.config_json_str = config_text
                            st.session_state.config_error = ""
                            st.success(f"✅ 已加载，共 {len(config.get('questions', []))} 道题")
                        except Exception as e:
                            st.session_state.config_error = f"解析失败: {e}"
                            st.error(st.session_state.config_error)
            else:
                # builtin
                try:
                    st.session_state.config = load_builtin_config()
                    st.session_state.config_error = ""
                    q_count = len(st.session_state.config.get("questions", []))
                    st.success(f"✅ 已加载内置配置，共 {q_count} 道题")
                except Exception as e:
                    st.session_state.config_error = f"加载内置配置失败: {e}"
                    st.error(st.session_state.config_error)

            # 显示当前配置预览
            if st.session_state.config is not None:
                with st.expander("📋 题目预览", expanded=False):
                    q_list = []
                    for q in st.session_state.config.get("questions", []):
                        q_list.append(f"- **{q['q_num']}** | {q['keyword']} | {q['max_score']}分")
                    st.markdown("\n".join(q_list))

        st.divider()

        # ── 评分控制 ──
        can_grade = (
            st.session_state.df is not None
            and st.session_state.config is not None
            and st.session_state.config_error == ""
            and st.session_state.sidebar_api_key.strip() != ""
            and st.session_state.grading_status == "idle"
        )

        if st.session_state.grading_status == "completed":
            st.success("✅ 评分已完成")

        st.button(
            "🚀 开始评分",
            type="primary",
            use_container_width=True,
            disabled=not can_grade,
            key="start_grading_btn",
            on_click=_on_start_grading,
        )

        if st.session_state.grading_status == "idle":
            if not can_grade:
                reasons = []
                if st.session_state.df is None:
                    reasons.append("❌ 未上传答卷")
                if st.session_state.config is None:
                    reasons.append("❌ 未加载评分配置")
                if st.session_state.config_error != "":
                    reasons.append(f"❌ 配置错误: {st.session_state.config_error}")
                if st.session_state.sidebar_api_key.strip() == "":
                    reasons.append("❌ 未填写 API Key")
                if not reasons:
                    reasons.append("✅ 所有条件已满足，按钮应该可点击")
                for r in reasons:
                    st.caption(r)
            else:
                st.caption("✅ 已就绪，点击按钮开始评分")
        elif st.session_state.grading_status == "running":
            st.info("⏳ 评分进行中...")
        elif st.session_state.grading_status == "paused":
            done = len(st.session_state.grading_results)
            total = st.session_state.get("grading_total", 0)
            st.warning(f"⏸️ 评分已暂停 ({done}/{total})")

        st.divider()

        # ── 下载 ──
        if st.session_state.grading_status == "completed":
            st.subheader("📥 下载报告")

            col1, col2 = st.columns(2)
            with col1:
                if st.session_state.excel_bytes is not None:
                    st.download_button(
                        label="📊 Excel",
                        data=st.session_state.excel_bytes,
                        file_name="AI阅卷结果报告.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
            with col2:
                if st.session_state.html_bytes is not None:
                    st.download_button(
                        label="🌐 HTML",
                        data=st.session_state.html_bytes,
                        file_name="AI阅卷结果报告.html",
                        mime="text/html",
                        use_container_width=True,
                    )


def _on_start_grading():
    """初始化评分队列，开始批量评分。"""
    st.session_state.grading_status = "running"
    st.session_state.grading_results = []
    st.session_state.grading_log = []
    st.session_state.reviewed_scores = {}

    # 解析候选人 → 构建评分队列（FIFO）
    df = st.session_state.df
    config = st.session_state.config
    candidates = parse_candidates(df)
    st.session_state.grading_queue = list(candidates)
    st.session_state.grading_total = len(candidates)

    # 构建原始作答查找表（供人工复核使用）
    st.session_state.candidate_answers = {}
    for name, school, answers in candidates:
        st.session_state.candidate_answers[name] = {
            q["keyword"]: answers.get(q.get("q_num", ""), "") for q in config["questions"]
        }

    # 同步 API 配置到环境变量 + 重新加载 ai_grader
    os.environ["AI_GRADER_API_KEY"] = st.session_state.sidebar_api_key.strip()
    os.environ["AI_GRADER_BASE_URL"] = st.session_state.sidebar_base_url.strip()
    os.environ["AI_GRADER_MODEL"] = st.session_state.sidebar_model.strip()
    importlib.reload(ai_grader)


# ============================================================
# 6. MAIN AREA — 上传区
# ============================================================

def render_upload_section():
    """Step 1: 上传 Excel 答卷文件。"""
    st.header("📂 Step 1: 上传答卷")

    uploaded_file = st.file_uploader(
        "拖拽或点击上传候选人答卷 Excel 文件 (.xlsx)",
        type=["xlsx"],
        key="main_uploader",
        help="Excel 第一行为表头，包含 Q1_ 姓名列、Q4_ 学校列、Q13_ 至 Q27_ 题目作答列",
    )

    if uploaded_file is not None:
        # 检测是否是新文件
        if st.session_state.uploaded_file_name != uploaded_file.name:
            st.session_state.uploaded_file_name = uploaded_file.name
            st.session_state.df = None
            st.session_state.parse_error = ""
            st.session_state.grading_status = "idle"
            st.session_state.grading_results = []
            st.session_state.grading_queue = []
            st.session_state.reviewed_scores = {}
            st.session_state.candidate_answers = {}

            try:
                df = pd.read_excel(uploaded_file)
                if df.empty:
                    st.session_state.parse_error = "Excel 文件为空"
                else:
                    st.session_state.df = df
            except Exception as e:
                st.session_state.parse_error = f"解析 Excel 失败: {e}"

        # 显示解析结果
        if st.session_state.parse_error:
            st.error(st.session_state.parse_error)
        elif st.session_state.df is not None:
            df = st.session_state.df
            candidates = parse_candidates(df)
            st.success(f"✅ 解析成功：{len(df)} 名候选人，{len(df.columns)} 列数据")

            # 预览表格
            with st.expander("🔍 数据预览（前 5 行）", expanded=True):
                # 截取关键列预览
                preview_cols = []
                for col in df.columns:
                    col_str = str(col)
                    if col_str.startswith('Q'):
                        preview_cols.append(col)
                # 有 Q 列就显示 Q 列，否则显示全部
                if preview_cols:
                    st.dataframe(df[preview_cols].head(5), use_container_width=True)
                else:
                    st.dataframe(df.head(5), use_container_width=True)

            # 候选人名单
            with st.expander("👥 候选人名单", expanded=False):
                names = [c[0] for c in candidates]
                schools = [c[1] for c in candidates]
                st.dataframe(
                    pd.DataFrame({"姓名": names, "学校": schools}),
                    use_container_width=True,
                )
    else:
        st.info("👆 请上传 .xlsx 格式的候选人答卷文件")
        # 引导提示
        with st.expander("📌 Excel 文件格式说明", expanded=False):
            st.markdown("""
            **必需列（表头前缀匹配）：**
            - `Q1_xxx` — 候选人姓名
            - `Q4_xxx` — 学校
            - `Q13_xxx` ~ `Q27_xxx` — 各题作答（对应 config.json 中的 15 道题）

            **示例表头：**
            | Q1_姓名 | Q4_学校 | Q13_语音连读标注 | Q14_长难句结构 | ... |
            """)


# ============================================================
# 7. MAIN AREA — 评分区
# ============================================================

def _render_live_ranking(results, total):
    """显示实时排名表（评分中途或暂停时）。"""
    df_live = pd.DataFrame(results)[["姓名", "学校", "总分"]]
    if not df_live.empty:
        df_live = df_live.sort_values("总分", ascending=False).reset_index(drop=True)
        df_live.index = df_live.index + 1
        df_live.index.name = "排名"
    st.markdown(f"**已完成 {len(results)}/{total} 名候选人**")
    st.dataframe(df_live, use_container_width=True)


def _grade_one_candidate(name, school, answers):
    """对单个候选人的所有题目进行 AI 评分，返回 candidate_report dict。"""
    config = st.session_state.config
    candidate_report = {"姓名": name, "学校": school, "总分": 0}
    total_score = 0

    for q in config["questions"]:
        q_num = q.get("q_num")
        keyword = q["keyword"]
        max_score = q["max_score"]

        answer = answers.get(q_num, "").strip()
        if not answer:
            answer = "未作答"

        if answer == "未作答":
            score, reason = 0, "候选人未作答"
        else:
            try:
                result = ai_grader.grade_single_question(
                    question_id=q.get("id", keyword),
                    candidate_answer=answer,
                    rubric=q["rubric"],
                    max_score=max_score,
                    background=q.get("background", ""),
                    reference_answer=q.get("reference_answer", ""),
                )
                time.sleep(1)  # API 限速

                if isinstance(result, dict):
                    score = result.get("score", 0)
                    reason = result.get("reason", "AI 未返回评价")
                else:
                    score, reason = result

                try:
                    score = int(score)
                except Exception:
                    score = 0

                if score < 0:
                    score = 0
                if score > max_score:
                    score = max_score
            except Exception as e:
                score = 0
                reason = f"AI 评分异常: {str(e)}"

        candidate_report[f"{keyword}_得分"] = score
        candidate_report[f"{keyword}_评价"] = reason
        total_score += score

    candidate_report["总分"] = total_score
    return candidate_report


def render_pause_controls():
    """渲染暂停/继续/停止按钮。"""
    status = st.session_state.grading_status

    if status == "running":
        if st.button("⏸️ 暂停评分", key="pause_grading_btn", use_container_width=True):
            st.session_state.grading_status = "paused"
            st.rerun()

    elif status == "paused":
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ 继续评分", key="resume_grading_btn",
                         use_container_width=True, type="primary"):
                st.session_state.grading_status = "running"
                st.rerun()
        with col2:
            if st.button("⏹️ 停止评分", key="stop_grading_btn",
                         use_container_width=True):
                st.session_state.grading_queue = []
                if st.session_state.grading_results:
                    st.session_state.grading_status = "completed"
                    _generate_download_files(st.session_state.grading_results)
                else:
                    st.session_state.grading_status = "idle"
                st.rerun()

        done = len(st.session_state.grading_results)
        total = st.session_state.get("grading_total", 0)
        remaining = len(st.session_state.grading_queue)
        st.info(f"📋 已完成 {done}/{total} 名候选人，剩余 {remaining} 名待评分")


def render_grading_section():
    """Step 2: AI 评分（批量模式 — 每次运行处理 1 人，支持暂停/续评）。"""
    st.header("🤖 Step 2: AI 评分")

    status = st.session_state.grading_status

    # ── idle ──
    if status == "idle":
        st.info("⚙️ 请在侧边栏配置 API 和评分配置，上传答卷后点击「开始评分」")
        return

    # ── paused ──
    if status == "paused":
        render_pause_controls()
        if st.session_state.grading_results:
            _render_live_ranking(st.session_state.grading_results,
                                st.session_state.get("grading_total", 0))
        return

    # ── completed ──
    if status == "completed":
        return

    # ── running ──
    # 渲染暂停按钮
    render_pause_controls()

    queue = st.session_state.grading_queue
    if not queue:
        # 队列为空 → 全部完成
        if st.session_state.grading_results:
            st.session_state.grading_status = "completed"
            _generate_download_files(st.session_state.grading_results)
            st.balloons()
        else:
            st.session_state.grading_status = "idle"
        st.rerun()

    # 取出队首候选人
    name, school, answers = queue[0]
    st.session_state.grading_queue = queue[1:]

    total = st.session_state.get("grading_total", 0)
    results = list(st.session_state.grading_results)
    done_before = len(results)
    current_idx = done_before + 1

    # UI 组件
    progress_bar = st.progress(done_before / total if total else 0)
    status_widget = st.status(f"🔍 评分 [{current_idx}/{total}]: {name} ({school})")
    live_table = st.empty()

    # 评分
    candidate_report = _grade_one_candidate(name, school, answers)
    results.append(candidate_report)

    # 更新 UI
    progress_bar.progress(current_idx / total)
    status_widget.update(label=f"✅ 完成 [{current_idx}/{total}]: {name} ({school}) — "
                              f"{candidate_report['总分']} 分")

    df_live = pd.DataFrame(results)[["姓名", "学校", "总分"]]
    if not df_live.empty:
        df_live = df_live.sort_values("总分", ascending=False).reset_index(drop=True)
        df_live.index = df_live.index + 1
        df_live.index.name = "排名"
    live_table.dataframe(df_live, use_container_width=True)

    # 持久化并继续下一个
    st.session_state.grading_results = results
    st.rerun()


def _generate_download_files(results):
    """生成 Excel 和 HTML 下载文件存入 session state。"""
    config = st.session_state.config
    df_results = pd.DataFrame(results)

    # 构建列顺序：姓名 → 学校 → 总分 → (每道题: 原始AI得分 → 最终得分 → 评价) → ...
    ordered = ["姓名", "学校", "总分"]
    for q in config["questions"]:
        kw = q["keyword"]
        oc = f"{kw}_原始得分"
        sc = f"{kw}_得分"
        rc = f"{kw}_评价"
        # 如果有原始得分列（表示被修改过）则加入
        if oc in df_results.columns:
            ordered.append(oc)
        if sc in df_results.columns:
            ordered.append(sc)
        if rc in df_results.columns:
            ordered.append(rc)

    # 追加其余未包含的列
    for c in df_results.columns:
        if c not in ordered:
            ordered.append(c)

    df_results = df_results[[c for c in ordered if c in df_results.columns]]

    excel_buffer = io.BytesIO()
    df_results.to_excel(excel_buffer, index=False)
    st.session_state.excel_bytes = excel_buffer.getvalue()

    # HTML — 修改标记已写入评价字段，html_report.py 无需修改
    import html_report
    html_buffer = io.BytesIO()
    tmp_path = os.path.join(BASE_DIR, "_tmp_report.html")
    try:
        html_report.generate_html_report(results, st.session_state.config, tmp_path)
        with open(tmp_path, "r", encoding="utf-8") as f:
            st.session_state.html_bytes = f.read().encode("utf-8")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ============================================================
# 7b. 人工复核
# ============================================================

def _apply_review_to_results(name, overrides):
    """将复核修改写入 grading_results，重新计算总分。"""
    config = st.session_state.config
    for r in st.session_state.grading_results:
        if r["姓名"] != name:
            continue

        total = 0
        for kw, ov in overrides.items():
            # 保留原始 AI 得分
            orig_key = f"{kw}_原始得分"
            if orig_key not in r:
                r[orig_key] = r.get(f"{kw}_得分", 0)

            # 更新得分
            r[f"{kw}_得分"] = ov["new_score"]

            # 在评价前面插入修改标记
            orig_reason = r.get(f"{kw}_评价", "")
            review_note = (
                f"【人工修改】原始: {ov['original_score']}分 → {ov['new_score']}分"
            )
            if ov.get("reason"):
                review_note += f"。修改理由: {ov['reason']}"

            if "【人工修改】" not in orig_reason:
                r[f"{kw}_评价"] = review_note + "\n\n---\n" + orig_reason
            else:
                # 已有修改标记 → 替换
                parts = orig_reason.split("---\n", 1)
                r[f"{kw}_评价"] = review_note + "\n\n---\n" + (parts[1] if len(parts) > 1 else "")

        # 重算总分
        for q in config["questions"]:
            total += r.get(f"{q['keyword']}_得分", 0)
        r["总分"] = total
        break


def _save_review(name):
    """保存某候选人的复核修改。"""
    config = st.session_state.config
    candidate = next((r for r in st.session_state.grading_results if r["姓名"] == name), None)
    if not candidate:
        return

    overrides = {}
    for q in config["questions"]:
        kw = q["keyword"]
        max_s = q["max_score"]
        ai_score = candidate.get(f"{kw}_得分", 0)

        # 从 widget 读取（key 格式：review_score_{name}_{keyword}）
        widget_key = f"review_score_{name}_{kw}"
        new_score = st.session_state.get(widget_key, ai_score)
        try:
            new_score = int(new_score)
        except (ValueError, TypeError):
            new_score = ai_score
        new_score = max(0, min(max_s, new_score))

        reason_key = f"review_reason_{name}_{kw}"
        new_reason = st.session_state.get(reason_key, "").strip()

        if new_score != ai_score or new_reason:
            overrides[kw] = {
                "original_score": ai_score,
                "new_score": new_score,
                "reason": new_reason,
            }

    if overrides:
        st.session_state.reviewed_scores[name] = overrides
        _apply_review_to_results(name, overrides)
        _generate_download_files(st.session_state.grading_results)
        st.success(f"✅ 已保存 {name} 的 {len(overrides)} 处修改")
    else:
        if name in st.session_state.reviewed_scores:
            _reset_review(name)
        st.info("未检测到修改")


def _reset_review(name):
    """撤销某候选人的所有复核修改，恢复 AI 原始评分。"""
    if name not in st.session_state.reviewed_scores:
        return

    overrides = st.session_state.reviewed_scores[name]
    config = st.session_state.config

    for r in st.session_state.grading_results:
        if r["姓名"] != name:
            continue

        total = 0
        for kw, ov in overrides.items():
            r[f"{kw}_得分"] = ov["original_score"]
            reason = r.get(f"{kw}_评价", "")
            if "【人工修改】" in reason:
                parts = reason.split("---\n", 1)
                r[f"{kw}_评价"] = parts[1] if len(parts) > 1 else ""
        for q in config["questions"]:
            total += r.get(f"{q['keyword']}_得分", 0)
        r["总分"] = total
        break

    del st.session_state.reviewed_scores[name]
    _generate_download_files(st.session_state.grading_results)
    st.success(f"✅ 已撤销 {name} 的所有修改")


def render_human_review_section():
    """Step 4: 人工复核 — 逐题查看 AI 评分并手动修改分数。"""
    if st.session_state.grading_status != "completed":
        return

    results = st.session_state.grading_results
    config = st.session_state.config
    if not results or not config:
        return

    st.divider()
    st.header("✏️ 人工复核")

    # 候选人选择
    sorted_results = sorted(results, key=lambda r: r["总分"], reverse=True)
    names = [r["姓名"] for r in sorted_results]
    selected = st.selectbox(
        "选择候选人进行复核",
        options=names,
        key="review_candidate_select",
    )

    if not selected:
        st.info("请从上方下拉框选择一位候选人进行复核")
        return

    candidate = next((r for r in results if r["姓名"] == selected), None)
    if not candidate:
        return

    # 候选人信息栏
    reviewed = st.session_state.reviewed_scores.get(selected, {})
    reviewed_count = len(reviewed)
    badge = f" 📝 ({reviewed_count}处已修改)" if reviewed_count > 0 else ""
    col_info, col_score = st.columns([3, 1])
    with col_info:
        st.subheader(f"📋 {selected}{badge}")
    with col_score:
        total = candidate.get("总分", 0)
        st.metric("总分", f"{total} 分")

    st.caption(f"📍 学校: {candidate.get('学校', '—')}")

    # 逐题复核
    for q in config["questions"]:
        kw = q["keyword"]
        max_s = q["max_score"]
        ai_score = candidate.get(f"{kw}_得分", 0)
        ai_reason = candidate.get(f"{kw}_评价", "")

        # 获取原始作答
        answer = st.session_state.candidate_answers.get(selected, {}).get(kw, "未找到作答")

        # 已有复核修改？
        existing = st.session_state.reviewed_scores.get(selected, {}).get(kw, {})
        is_modified = bool(existing)

        with st.container():
            st.markdown("---")
            col_title, col_badge = st.columns([4, 1])
            with col_title:
                st.markdown(f"**{kw}** (满分 {max_s} 分)")
            with col_badge:
                if is_modified:
                    st.markdown(
                        f'<span style="color:#e53935;font-weight:bold">'
                        f'🔴 {existing["original_score"]} → {existing["new_score"]} 分</span>',
                        unsafe_allow_html=True,
                    )

            col_answer, col_score_review = st.columns([1, 2])

            with col_answer:
                st.text_area(
                    "候选人作答",
                    value=answer,
                    height=120,
                    disabled=True,
                    key=f"answer_{selected}_{kw}",
                    label_visibility="collapsed",
                )

            with col_score_review:
                # AI 评分展示
                st.info(
                    f"🤖 AI评分: **{ai_score}/{max_s}** 分\n\n"
                    f"{ai_reason[:300]}{'...' if len(ai_reason) > 300 else ''}"
                )

                # 修改分数
                default_new_score = existing.get("new_score", ai_score)
                new_score = st.number_input(
                    "修改分数",
                    min_value=0,
                    max_value=max_s,
                    value=int(default_new_score),
                    key=f"review_score_{selected}_{kw}",
                )
                new_reason = st.text_input(
                    "修改理由（可选）",
                    value=existing.get("reason", ""),
                    key=f"review_reason_{selected}_{kw}",
                    placeholder="输入修改理由...",
                )

    st.markdown("---")

    # 操作按钮
    col_save, col_reset = st.columns([2, 1])
    with col_save:
        if st.button("💾 保存修改", type="primary",
                     key=f"save_review_{selected}", use_container_width=True):
            _save_review(selected)
            st.rerun()
    with col_reset:
        if reviewed_count > 0:
            if st.button("🔄 撤销所有修改",
                        key=f"reset_review_{selected}", use_container_width=True):
                _reset_review(selected)
                st.rerun()


# ============================================================
# 8. MAIN AREA — Dashboard
# ============================================================

def render_dashboard():
    """Step 3: 结果 Dashboard。"""
    if st.session_state.grading_status != "completed":
        return

    results = st.session_state.grading_results
    config = st.session_state.config

    if not results:
        return

    st.header("📊 Step 3: 评分结果")

    # ── 摘要指标 ──
    st.subheader("概览")
    n = len(results)
    totals = [r["总分"] for r in results]
    avg_total = round(sum(totals) / n, 1) if n else 0
    max_total = max(totals) if totals else 0
    min_total = min(totals) if totals else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("👥 候选人", f"{n} 人")
    col2.metric("📊 平均总分", f"{avg_total} 分")
    col3.metric("🏆 最高分", f"{max_total} 分")
    col4.metric("📉 最低分", f"{min_total} 分")

    st.divider()

    # ── 各题得分趋势图 ──
    st.subheader("📈 各题得分趋势")
    stats = compute_question_stats(results, config)
    fig_line = build_score_line_chart(stats)
    st.plotly_chart(fig_line, use_container_width=True)

    st.divider()

    # ── 排名表 ──
    st.subheader("🏆 候选人排名")
    ranking_df = build_ranking_df(results)

    # 添加复核标记列
    reviewed_names = set(st.session_state.reviewed_scores.keys())
    ranking_df["复核"] = ranking_df["姓名"].apply(
        lambda n: "✅" if n in reviewed_names else ""
    )

    # 高亮显示得分列的颜色
    score_cols = [c for c in ranking_df.columns if c.endswith("_得分")]

    def color_scores(val):
        """为得分单元格着色。"""
        if isinstance(val, (int, float)):
            if val >= 8:
                return "background-color: #c8e6c9"
            elif val >= 5:
                return "background-color: #fff9c4"
            else:
                return "background-color: #ffcdd2"
        return ""

    styled = ranking_df.style.map(color_scores, subset=score_cols)
    st.dataframe(styled, use_container_width=True, height=400)

    st.divider()

    # ── 候选人详情 ──
    st.subheader("🔍 候选人作答详情")

    sorted_results = sorted(results, key=lambda r: r["总分"], reverse=True)
    names = [r["姓名"] for r in sorted_results]

    selected = st.selectbox(
        "选择候选人查看详情",
        options=names,
        key="dashboard_candidate_select",
    )

    if selected:
        candidate = next((r for r in results if r["姓名"] == selected), None)
        if candidate:
            # 构建详情表
            detail_rows = []
            reviewed = st.session_state.reviewed_scores.get(selected, {})
            for q in config["questions"]:
                kw = q["keyword"]
                score = candidate.get(f"{kw}_得分", 0)
                reason = candidate.get(f"{kw}_评价", "")
                max_s = q["max_score"]
                pct = round(score / max_s * 100, 1) if max_s > 0 else 0

                if pct >= 80:
                    badge = "🟢"
                elif pct >= 50:
                    badge = "🟠"
                else:
                    badge = "🔴"

                # 复核标记
                review_info = reviewed.get(kw, {})
                if review_info:
                    orig = review_info["original_score"]
                    score_display = f"{score} / {max_s} (原始: {orig})"
                    badge += " ✏️"
                else:
                    score_display = f"{score} / {max_s}"

                detail_rows.append({
                    "题目": kw,
                    "得分/满分": score_display,
                    "得分率": f"{badge} {pct}%",
                    "AI 评价": reason[:200] + ("..." if len(reason) > 200 else ""),
                    "_full_reason": reason,
                    "_reviewed": bool(review_info),
                })

            detail_df = pd.DataFrame(detail_rows)
            display_df = detail_df[["题目", "得分/满分", "得分率", "AI 评价"]]

            # 为每行创建 expander 显示完整理由
            for i, row in detail_df.iterrows():
                cols = st.columns([2, 1, 1, 4])
                cols[0].write(row["题目"])
                cols[1].write(row["得分/满分"])
                cols[2].write(row["得分率"])
                with cols[3]:
                    with st.expander("查看 AI 评价"):
                        st.markdown(
                            f'<div style="max-height:200px;overflow-y:auto;padding:8px;'
                            f'background:#fafafa;border-left:3px solid #1a237e;border-radius:0 6px 6px 0;'
                            f'font-size:0.88rem;white-space:pre-wrap;">{row["_full_reason"]}</div>',
                            unsafe_allow_html=True,
                        )

            # 学校 + 总分
            st.caption(f"📍 学校: {candidate.get('学校', '—')} | 总分: **{candidate['总分']} 分**")

    st.divider()

    # ── 能力画像雷达图 ──
    st.subheader("🧠 综合能力画像")

    groups = derive_competency_groups(config)
    comp_scores = compute_competency_scores(results, groups)
    dim_labels = list(groups.keys())

    if not dim_labels:
        st.warning("暂无能力维度数据")
        return

    # Grid 布局: 每行 3 个雷达图
    COLS_PER_ROW = 3
    for i in range(0, len(comp_scores), COLS_PER_ROW):
        batch = comp_scores[i:i + COLS_PER_ROW]
        cols = st.columns(len(batch))
        for col, c in zip(cols, batch):
            with col:
                fig = build_radar_chart(c, dim_labels)
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{i}_{c['name']}")


# ============================================================
# 9. TOP-LEVEL FLOW
# ============================================================

def main():
    init_session_state()
    render_sidebar()

    # ── 主区域 ──
    render_upload_section()
    st.divider()
    render_grading_section()
    render_dashboard()
    render_human_review_section()

    # ── Footer ──
    st.divider()
    st.caption(
        f"AI 阅卷平台 · Streamlit Phase 2 · "
        f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


if __name__ == "__main__":
    main()
