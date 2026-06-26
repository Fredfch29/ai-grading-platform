import json
import os
import time
import pandas as pd
from excel_parser import parse_real_candidates_excel
from ai_grader import grade_single_question


# 以脚本所在目录为基准，确保无论从哪里运行都能找到文件
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    # 1. 配置文件路径
    excel_file = os.path.join(BASE_DIR, "笔试6.25.xlsx")
    config_file = os.path.join(BASE_DIR, "config.json")
    output_file = os.path.join(BASE_DIR, "AI阅卷结果报告.xlsx")

   # 2. 加载打分配置
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"✅ 成功加载打分标准，共配置了 {len(config['questions'])} 道大题。")
    except Exception as e:
        print(f"❌ 读取 config.json 失败: {e}")
        return

    # 3. 直接使用 pandas 解析候选人答卷 (取代原有的 parse_real_candidates_excel)
    try:
        df = pd.read_excel(excel_file)
    except Exception as e:
        print(f"❌ 读取 Excel 失败: {e}")
        return

    if df.empty:
        print("❌ 未获取到候选人数据，程序退出。")
        return

    # 4. 自动化批量阅卷
    print("\n🚀 开始 AI 自动化阅卷...")
    all_results = []
    total_candidates = len(df)

    for idx, row in df.iterrows():
        # --- 智能提取基础信息（姓名和学校也使用前缀匹配，防重防错） ---
        name = f"未知候选人_{idx + 1}"
        school = "未知学校"
        
        for col in df.columns:
            col_str = str(col)
            if col_str.startswith('Q1_'):
                # 排除空值
                name = str(row[col]).strip() if pd.notna(row[col]) else name
            elif col_str.startswith('Q4_'):
                school = str(row[col]).strip() if pd.notna(row[col]) else school

        print(f"\n[{idx + 1}/{total_candidates}] 正在批阅: {name} ({school})")

        # 构建该候选人的成绩单字典
        candidate_report = {
            "姓名": name,
            "学校": school,
            "总分": 0
        }

        # 遍历配置好的题目进行打分
        total_score = 0
        for q in config['questions']:
            q_num = q.get('q_num')  # 👈 获取我们在 config 中新增的 Q13 等编号
            keyword = q['keyword']
            
            # --- 核心：模糊匹配 Excel 表头，寻找对应的题目列 ---
            actual_col_name = None
            for col in df.columns:
                col_str = str(col)
                # 匹配 "Q13_" 开头，或完全等于 "Q13"
                if col_str.startswith(f"{q_num}_") or col_str == q_num:
                    actual_col_name = col
                    break
            
            # 安全提取答案
            if actual_col_name is not None and pd.notna(row[actual_col_name]):
                answer = str(row[actual_col_name]).strip()
                if not answer:  # 如果全是空格
                    answer = "未作答"
            else:
                answer = "未作答"

            print(f"  👉 正在打分: {keyword}...", end="", flush=True)

            # 如果未作答直接给0分，否则调用大模型
            if answer == "未作答":
                score, reason = 0, "候选人未作答"
            else:
                # 调用 AI_grader，支持返回 tuple 或 dict 两种情况
                result = grade_single_question(
                    question_id=q.get('id', keyword),
                    candidate_answer=answer,
                    rubric=q['rubric'],
                    max_score=q['max_score'],
                    background=q.get('background', ''),  
                    reference_answer=q.get('reference_answer', '')  
                )

                # 停顿1秒，防止请求过快被大模型 API 限制 (Rate Limit)
                time.sleep(1)

                if isinstance(result, dict):
                    score = result.get('score', 0)
                    reason = result.get('reason', 'AI 未返回评价')
                else:
                    score, reason = result

                try:
                    score = int(score)
                except Exception:
                    score = 0

                if score < 0:
                    score = 0
                if score > q['max_score']:
                    score = q['max_score']

            print(f" 得分: {score}/{q['max_score']}")

            # 记入成绩单
            candidate_report[f"{keyword}_得分"] = score
            candidate_report[f"{keyword}_评价"] = reason
            total_score += score

        candidate_report["总分"] = total_score
        all_results.append(candidate_report)

    # 5. 导出结果到新的 Excel
    df_results = pd.DataFrame(all_results)

    # 把“总分”列移动到姓名和学校后面，方便查看
    cols = df_results.columns.tolist()
    if '总分' in cols:
        cols.insert(2, cols.pop(cols.index('总分')))
        df_results = df_results[cols]

    df_results.to_excel(output_file, index=False)
    print(f"\n🎉 阅卷全部完成！共有 {total_candidates} 份答卷被批阅。")
    print(f"💾 成绩单已保存: {output_file}")

    # 6. 生成 HTML 可视化报告
    from html_report import generate_html_report
    html_path = os.path.join(BASE_DIR, "AI阅卷结果报告.html")
    generate_html_report(all_results, config, html_path)
    print(f"📊 HTML 报告已保存: {html_path}")


if __name__ == "__main__":
    main()