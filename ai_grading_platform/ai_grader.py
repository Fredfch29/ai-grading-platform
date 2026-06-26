import json
from openai import OpenAI

# ==========================================
# ⚠️ 第一步：配置大模型 API
# 通过环境变量设置，避免 API Key 泄露到代码仓库
#   export AI_GRADER_API_KEY="sk-xxx"
#   export AI_GRADER_BASE_URL="https://api.deepseek.com"
#   export AI_GRADER_MODEL="deepseek-v4-pro"
# ==========================================
import os

# 自动加载 .env 文件（依次查找脚本所在目录 → 上级目录 → 上上级目录）
_ENV_DIRS = [
    os.path.dirname(os.path.abspath(__file__)),
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
]
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

API_KEY = os.getenv("AI_GRADER_API_KEY", "")
BASE_URL = os.getenv("AI_GRADER_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.getenv("AI_GRADER_MODEL", "deepseek-v4-pro")

# 初始化 OpenAI 客户端
if not API_KEY:
    raise RuntimeError(
        "❌ 未设置 AI_GRADER_API_KEY 环境变量。\n"
        "请在终端中运行：\n"
        "  export AI_GRADER_API_KEY=\"sk-你的API密钥\"\n"
        "或在项目根目录创建 .env 文件（参考 .env.example）"
    )

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)


def grade_single_question(question_id, candidate_answer, rubric, max_score, background="", reference_answer=""):
    """
    调用 AI 给单道题打分的核心函数。
    支持动态传入 background(背景材料) 和 reference_answer(参考答案)。
    """

    # 1. 动态拼接条件：只有在配置文件里写了这两个字段，才会拼进提示词里
    bg_text = f"【背景/阅读材料】:\n{background}\n" if background else ""
    ref_text = f"【参考答案】:\n{reference_answer}\n" if reference_answer else ""

    # 2. 构建严谨的 Prompt
    prompt = f"""你是一位严厉且公平的资深阅卷专家。请根据以下信息对候选人的作答进行打分。

{bg_text}
【题目 ID】: {question_id}
【满分分值】: {max_score}
{ref_text}
【打分标准 (Rubric)】: 
{rubric}

【候选人作答】: 
{candidate_answer}

请严格对照“打分标准”，评估候选人的作答。
【输出要求】:
必须且只能返回一个合法的 JSON 格式字符串，不要包含任何 markdown 修饰符（如 ```json），确保可以直接被 json.loads 解析。
JSON 必须包含以下两个字段：
- "score": 具体分数 (必须是整数，且不能超过满分)
- "reason": 给分理由 (简明扼要，指出具体的得分点或失分点)
"""

    try:
        # 3. 发送请求给大模型
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一个严谨的AI自动阅卷系统。你只输出纯正的 JSON 格式结果。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # 阅卷需要确定性，把 temperature 调低防止 AI 乱发散
        )

        # 获取大模型的回复文本
        result_str = response.choices[0].message.content.strip()

        # 4. 防错机制：清理大模型有时喜欢乱加的 markdown 代码块符号
        if result_str.startswith("```json"):
            result_str = result_str[7:]
        elif result_str.startswith("```"):
            result_str = result_str[3:]

        if result_str.endswith("```"):
            result_str = result_str[:-3]

        result_str = result_str.strip()

        # 5. 解析为 Python 字典
        result_dict = json.loads(result_str)

        # 6. 返回 score 和 reason 两个值，避免调用方误解字典解包问题
        score = result_dict.get("score", 0)
        reason = result_dict.get("reason", "AI 未返回评价")
        try:
            score = int(score)
        except Exception:
            score = 0

        return score, reason

    except Exception as e:
        print(f"\n❌ 调用 AI 失败 ({question_id}): {e}")
        return 0, f"AI 打分异常，未获取到有效评价。错误信息: {str(e)}"