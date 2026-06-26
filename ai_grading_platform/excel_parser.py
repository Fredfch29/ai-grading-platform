import pandas as pd


def parse_real_candidates_excel(file_path):
    """
    解析真实的横向候选人 Excel 答卷
    返回一个列表，列表里每个元素代表一个候选人的字典，包含 personal_info 和 answers
    """
    try:
        # 读取整个 Excel，默认第一行为表头
        df = pd.read_excel(file_path)

        # 过滤掉未成功提交的数据（根据你的真实数据列名）
        if '完成状态' in df.columns:
            df = df[df['完成状态'] == '成功']

        candidates_data = []

        for index, row in df.iterrows():
            personal_info = {}
            answers = {}

            for col_name in df.columns:
                # 处理空值，替换为 "未作答"
                val = str(row[col_name]).strip() if pd.notna(row[col_name]) and str(row[col_name]) != 'nan' else "未作答"

                # 根据真实表头特征分类：Q1到Q12以及系统状态属于个人信息
                if col_name.startswith(
                        ('完成状态', '答案唯一标识', 'Q1_', 'Q2_', 'Q3_', 'Q4_', 'Q5_', 'Q6_', 'Q7_', 'Q8_', 'Q9_',
                         'Q10_', 'Q11_', 'Q12_')):
                    personal_info[col_name] = val
                else:
                    # Q13 及以后的题目都属于笔试作答区域
                    answers[col_name] = val

            candidates_data.append({
                "personal_info": personal_info,
                "answers": answers
            })

        print(f"✅ 成功解析文件: {file_path}")
        print(f"🎉 共提取到 {len(candidates_data)} 位候选人的有效答卷！\n")
        return candidates_data

    except Exception as e:
        print(f"❌ 解析 Excel 失败: {e}")
        return None


# --- 测试一下解析逻辑 ---
if __name__ == "__main__":
    # 将这里替换为你真实的 excel 文件名
    test_file = r"C:\Users\fuzhanghui\Desktop\ai_grading_platform\笔试6.25.xlsx"
    candidates = parse_real_candidates_excel(test_file)

    if candidates:
        # 打印第一个候选人的信息预览
        first_candidate = candidates[0]
        print(f"▶ 预览第一位候选人：{first_candidate['personal_info'].get('Q1_您的姓名：', '未知')}")
        print(
            f"- 毕业院校: {first_candidate['personal_info'].get('Q4_您的学校是：研究生同学请填写本科及研究生阶段所就读的学校，填写格式为：本科：XX大学；研究生：XX大学', '未知')}")
        print(f"- Q24(幻觉)作答预览: {first_candidate['answers'].get('Q24_Hallucination', '')[:30]}...")