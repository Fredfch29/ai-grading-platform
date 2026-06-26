"""
HTML 可视化报告生成器
=====================
从阅卷结果生成一份自包含的 HTML 报告，包含：
- 各题得分统计折线图（Chart.js）
- 候选人作答详情（含 AI 打分理由）
- 综合能力画像雷达图
"""

import json
from datetime import datetime

# ============================================================
# 能力维度映射：根据 config 中题目的 "id" 字段，自动归入 7 大维度
# ============================================================
COMPETENCY_LABEL_MAP = {
    "连读记号标注": "语音标注能力",
    "英语语法分析": "语法分析能力",
    "中译英翻译":   "中译英能力",
    "英译中翻译":   "英译中能力",
    "翻译质量评估": "翻译评估能力",
    "AI术语简述":   "AI基础认知",
    "AI评测分析":   "AI评测设计能力",
    "系统指令撰写": "AI评测设计能力",  # 与上一条合并
}


# ============================================================
# 1. 数据计算层
# ============================================================

def _compute_question_stats(all_results, config):
    """计算每道题的 min / max / avg 得分。"""
    questions = config["questions"]
    stats = []
    for q in questions:
        keyword = q["keyword"]
        key = f"{keyword}_得分"
        scores = [r[key] for r in all_results if key in r and isinstance(r[key], (int, float))]
        stats.append({
            "keyword": keyword,
            "max_possible": q["max_score"],
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "avg": round(sum(scores) / len(scores), 1) if scores else 0,
        })
    return stats


def _derive_competency_groups(config):
    """根据 config 的 id 字段和 COMPETENCY_LABEL_MAP 自动派生能力维度分组。"""
    groups = {}  # { label: [(keyword, max_score), ...] }
    unmapped = set()

    for q in config["questions"]:
        qid = q.get("id", "")
        label = COMPETENCY_LABEL_MAP.get(qid)
        if label is None:
            unmapped.add(qid)
            # 未映射的题目归入 catch-all 维度
            label = "其他能力"
        groups.setdefault(label, []).append((q["keyword"], q["max_score"]))

    if unmapped:
        print(f"⚠️ 以下题目 id 未在能力维度映射中，已归入「其他能力」: {unmapped}")
    return groups


def _compute_competency_scores(all_results, competency_groups):
    """为每个候选人计算各能力维度的得分率 (0-100)。"""
    comp_scores = []
    for candidate in all_results:
        name = candidate["姓名"]
        total = candidate["总分"]
        dims = {}
        for label, items in competency_groups.items():
            actual = sum(candidate.get(f"{kw}_得分", 0) for kw, _ in items)
            max_possible = sum(ms for _, ms in items)
            pct = round(actual / max_possible * 100, 1) if max_possible > 0 else 0
            dims[label] = pct
        comp_scores.append({"name": name, "total": total, "dimensions": dims})
    # 按总分降序
    comp_scores.sort(key=lambda x: x["total"], reverse=True)
    return comp_scores


# ============================================================
# 2. HTML 片段构建层
# ============================================================

def _build_head():
    """返回 <head> 区（meta / 样式 / Chart.js CDN）。"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 阅卷结果报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js">
</script>
<style>
  :root {
    --primary: #1a237e;
    --primary-light: #283593;
    --bg: #f5f6fa;
    --card: #ffffff;
    --text: #212121;
    --muted: #666;
    --green: #2e7d32;
    --orange: #f57c00;
    --red: #c62828;
    --radius: 10px;
    --shadow: 0 2px 12px rgba(0,0,0,0.07);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Helvetica Neue", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 20px;
  }
  .container { max-width: 1200px; margin: 0 auto; }

  /* Header */
  .report-header {
    background: linear-gradient(135deg, var(--primary), var(--primary-light));
    color: #fff;
    padding: 32px 36px;
    border-radius: var(--radius);
    margin-bottom: 28px;
  }
  .report-header h1 { font-size: 1.8rem; font-weight: 700; margin-bottom: 8px; }
  .report-header .meta { display: flex; gap: 28px; flex-wrap: wrap; font-size: 0.92rem; opacity: 0.9; }
  .report-header .meta span { white-space: nowrap; }
  .report-header .avg-score {
    margin-top: 10px;
    font-size: 1.2rem;
    font-weight: 600;
  }

  /* Card */
  .card {
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 28px 32px;
    margin-bottom: 24px;
  }
  .card h2 {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 18px;
    padding-bottom: 10px;
    border-bottom: 2px solid #e8eaf6;
  }

  /* Section 1: Chart */
  .chart-wrap {
    position: relative;
    width: 100%;
    height: 420px;
    margin-bottom: 24px;
  }
  .chart-wrap canvas { width: 100% !important; height: 100% !important; }

  /* Ranking Table */
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
  }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #e8eaf6; color: var(--primary); font-weight: 600; white-space: nowrap; }
  tr:hover { background: #f5f5ff; }
  .rank-badge {
    display: inline-block;
    width: 26px; height: 26px; line-height: 26px;
    text-align: center; border-radius: 50%;
    color: #fff; font-weight: 700; font-size: 0.82rem;
  }
  .rank-1 { background: #f9a825; }
  .rank-2 { background: #90a4ae; }
  .rank-3 { background: #a1887f; }
  .rank-other { background: #b0bec5; }

  /* Section 2: Dropdown + Detail */
  .candidate-select {
    font-size: 1rem;
    padding: 8px 14px;
    border: 1px solid #ccc;
    border-radius: 6px;
    margin-bottom: 20px;
    min-width: 280px;
    background: #fff;
  }
  .score-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 0.85rem;
    color: #fff;
  }
  .score-high { background: var(--green); }
  .score-mid  { background: var(--orange); }
  .score-low  { background: var(--red); }

  details { margin-top: 4px; }
  summary {
    cursor: pointer;
    color: var(--primary);
    font-weight: 500;
    font-size: 0.88rem;
    user-select: none;
  }
  summary:hover { text-decoration: underline; }
  .reason-text {
    margin-top: 6px;
    padding: 10px 14px;
    background: #fafafa;
    border-left: 3px solid var(--primary-light);
    border-radius: 0 6px 6px 0;
    font-size: 0.88rem;
    color: #444;
    max-height: 200px;
    overflow-y: auto;
    white-space: pre-wrap;
  }

  /* Section 3: Radar Grid */
  .radar-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
  }
  .radar-card {
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 20px;
    text-align: center;
  }
  .radar-card .name { font-weight: 700; font-size: 1.05rem; margin-bottom: 2px; }
  .radar-card .total { color: var(--muted); font-size: 0.85rem; margin-bottom: 10px; }
  .radar-card .radar-wrap {
    position: relative;
    width: 100%;
    max-width: 340px;
    margin: 0 auto;
  }

  /* CDN fallback */
  .cdn-warning {
    display: none;
    background: #fff3e0;
    color: #e65100;
    padding: 10px 18px;
    border-radius: 6px;
    margin-bottom: 20px;
    font-weight: 600;
  }

  /* Responsive */
  @media (max-width: 768px) {
    body { padding: 10px; }
    .report-header { padding: 20px; }
    .report-header .meta { flex-direction: column; gap: 4px; }
    .card { padding: 16px; }
    .radar-grid { grid-template-columns: 1fr; }
    .chart-wrap { height: 300px; }
  }
</style>
</head>
"""


def _build_header(all_results, config):
    """报告顶部横幅。"""
    n = len(all_results)
    avg_total = round(sum(r["总分"] for r in all_results) / n, 1) if n else 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""
<body>
<div id="cdn-warning" class="cdn-warning container">
  ⚠️ Chart.js 图表库加载失败（需要网络连接），图表部分将无法显示。请检查网络后刷新页面。
</div>
<div class="container">
  <div class="report-header">
    <h1>📋 AI 阅卷结果报告</h1>
    <div class="meta">
      <span>🕐 生成时间：{now}</span>
      <span>👥 候选人：{n} 人</span>
      <span>📝 题目数：{len(config['questions'])} 道</span>
    </div>
    <div class="avg-score">📊 平均总分：{avg_total} 分</div>
  </div>
"""


def _build_overview_section(stats):
    """题目得分折线图 + 排名表。"""
    lines = []
    lines.append('<div class="card">')
    lines.append('<h2>📈 各题得分统计</h2>')
    # 折线图 canvas
    lines.append('<div class="chart-wrap"><canvas id="scoreLineChart"></canvas></div>')
    lines.append('</div>')
    return "\n".join(lines)


def _build_ranking_table(all_results):
    """总分排名表。"""
    rows = []
    rows.append('<div class="card">')
    rows.append('<h2>🏆 总分排名</h2>')
    rows.append('<table><thead><tr><th>排名</th><th>姓名</th><th>学校</th><th>总分</th></tr></thead><tbody>')

    sorted_results = sorted(all_results, key=lambda r: r["总分"], reverse=True)
    for i, r in enumerate(sorted_results):
        rank = i + 1
        if rank == 1:
            cls = "rank-1"
        elif rank == 2:
            cls = "rank-2"
        elif rank == 3:
            cls = "rank-3"
        else:
            cls = "rank-other"
        rows.append(
            f'<tr><td><span class="rank-badge {cls}">{rank}</span></td>'
            f'<td><strong>{_esc(r["姓名"])}</strong></td>'
            f'<td>{_esc(r["学校"])}</td>'
            f'<td><strong>{r["总分"]}</strong></td></tr>'
        )
    rows.append('</tbody></table>')
    rows.append('</div>')
    return "\n".join(rows)


def _build_candidate_detail_section(all_results):
    """候选人详情：下拉框 + 动态表格容器。"""
    # 按总分降序
    sorted_results = sorted(all_results, key=lambda r: r["总分"], reverse=True)
    opts = []
    for r in sorted_results:
        opts.append(f'<option value="{_esc(r["姓名"])}">{_esc(r["姓名"])} ({r["总分"]}分)</option>')

    return f"""
<div class="card">
  <h2>🔍 候选人作答详情</h2>
  <select class="candidate-select" id="candidateSelect" onchange="renderDetail()">
    {"".join(opts)}
  </select>
  <div id="detailContainer">
    <p style="color:var(--muted)">请从上方下拉框选择一位候选人查看详情。</p>
  </div>
</div>
"""


def _build_competency_section(comp_scores, all_dim_labels):
    """每个候选人一张雷达图卡片。"""
    cards = []
    for i, c in enumerate(comp_scores):
        cards.append(f"""
<div class="radar-card">
  <div class="name">{_esc(c["name"])}</div>
  <div class="total">总分 {c["total"]} 分</div>
  <div class="radar-wrap">
    <canvas id="radar_{i}"></canvas>
  </div>
</div>""")
    return f"""
<div class="card">
  <h2>🧠 综合能力画像</h2>
  <div class="radar-grid">
    {"".join(cards)}
  </div>
</div>
"""


def _build_scripts(all_results, config, stats, comp_scores):
    """生成所有 inline JavaScript。"""
    # 准备 JS 数据
    questions_list = config["questions"]

    # --- 候选人详情数据 ---
    candidates_data = {}
    for r in all_results:
        name = r["姓名"]
        q_items = []
        for q in questions_list:
            kw = q["keyword"]
            score = r.get(f"{kw}_得分", 0)
            reason = r.get(f"{kw}_评价", "")
            max_s = q["max_score"]
            pct = round(score / max_s * 100, 1) if max_s > 0 else 0
            q_items.append({
                "keyword": kw,
                "score": score,
                "max": max_s,
                "pct": pct,
                "reason": reason,
            })
        candidates_data[name] = {
            "name": name,
            "school": r.get("学校", ""),
            "total": r["总分"],
            "questions": q_items,
        }

    # --- 能力画像数据 ---
    comp_data = []
    for c in comp_scores:
        comp_data.append({
            "name": c["name"],
            "total": c["total"],
            "dimensions": c["dimensions"],
        })
    dim_labels = list(comp_scores[0]["dimensions"].keys()) if comp_scores else []

    # --- 折线图数据 ---
    chart_labels = [s["keyword"] for s in stats]
    chart_max_scores = [s["max"] for s in stats]
    chart_avg_scores = [s["avg"] for s in stats]
    chart_min_scores = [s["min"] for s in stats]

    js_data = {
        "candidatesData": candidates_data,
        "competency": comp_data,
        "dimLabels": dim_labels,
        "chartLabels": chart_labels,
        "chartMax": chart_max_scores,
        "chartAvg": chart_avg_scores,
        "chartMin": chart_min_scores,
    }

    return f"""
<script>
// ===== 嵌入数据 =====
const REPORT = {json.dumps(js_data, ensure_ascii=False, indent=2)};

// ===== Chart.js 加载检测 =====
window.addEventListener('DOMContentLoaded', () => {{
  setTimeout(() => {{
    if (typeof Chart === 'undefined') {{
      document.getElementById('cdn-warning').style.display = 'block';
    }}
  }}, 3000);
}});

// ===== 工具函数 =====
function esc(s) {{
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}}

function badgeClass(pct) {{
  if (pct >= 80) return 'score-high';
  if (pct >= 50) return 'score-mid';
  return 'score-low';
}}

// ===== Section 1: Score Line Chart =====
function initLineChart() {{
  if (typeof Chart === 'undefined') return;
  const ctx = document.getElementById('scoreLineChart');
  if (!ctx) return;
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: REPORT.chartLabels,
      datasets: [
        {{
          label: '最高分',
          data: REPORT.chartMax,
          borderColor: '#e53935',
          backgroundColor: 'rgba(229,57,53,0.08)',
          tension: 0.3,
          pointRadius: 6,
          pointBackgroundColor: '#e53935',
          borderWidth: 2.5,
        }},
        {{
          label: '平均分',
          data: REPORT.chartAvg,
          borderColor: '#1e88e5',
          backgroundColor: 'rgba(30,136,229,0.08)',
          tension: 0.3,
          pointRadius: 6,
          pointBackgroundColor: '#1e88e5',
          borderWidth: 2.5,
        }},
        {{
          label: '最低分',
          data: REPORT.chartMin,
          borderColor: '#43a047',
          backgroundColor: 'rgba(67,160,71,0.08)',
          tension: 0.3,
          pointRadius: 6,
          pointBackgroundColor: '#43a047',
          borderWidth: 2.5,
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ intersect: false, mode: 'index' }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: ctx => `${{ctx.dataset.label}}: ${{ctx.raw}} 分`
          }}
        }}
      }},
      scales: {{
        y: {{
          beginAtZero: true,
          title: {{ display: true, text: '得分', font: {{ size: 13 }} }},
          ticks: {{ stepSize: 1 }}
        }},
        x: {{
          ticks: {{ maxRotation: 50, minRotation: 0, font: {{ size: 11 }} }}
        }}
      }}
    }}
  }});
}}

// ===== Section 2: Candidate Detail =====
function renderDetail() {{
  const select = document.getElementById('candidateSelect');
  const container = document.getElementById('detailContainer');
  const name = select.value;
  const data = REPORT.candidatesData[name];
  if (!data) {{ container.innerHTML = '<p>未找到候选人数据。</p>'; return; }}

  let html = '<table><thead><tr><th>题目</th><th>得分 / 满分</th><th>得分率</th><th>AI 打分理由</th></tr></thead><tbody>';
  for (const q of data.questions) {{
    html += `<tr>
      <td><strong>${{esc(q.keyword)}}</strong></td>
      <td>${{q.score}} / ${{q.max}}</td>
      <td><span class="score-badge ${{badgeClass(q.pct)}}">${{q.pct}}%</span></td>
      <td>
        <details>
          <summary>查看 AI 评价</summary>
          <div class="reason-text">${{esc(q.reason)}}</div>
        </details>
      </td>
    </tr>`;
  }}
  html += '</tbody></table>';
  html += `<p style="margin-top:10px;">📍 学校: ${{esc(data.school)}} | 总分: <strong>${{data.total}}</strong></p>`;
  container.innerHTML = html;
}}

// ===== Section 3: Radar Charts =====
function initRadarCharts() {{
  if (typeof Chart === 'undefined') return;
  const data = REPORT.competency;
  const labels = REPORT.dimLabels;
  if (!labels.length) return;

  const colors = [
    {{ bg: 'rgba(26,35,126,0.18)', border: '#1a237e' }},
    {{ bg: 'rgba(0,121,107,0.18)', border: '#00796b' }},
    {{ bg: 'rgba(194,24,91,0.18)', border: '#c2185b' }},
    {{ bg: 'rgba(230,81,0,0.18)', border: '#e65100' }},
    {{ bg: 'rgba(21,101,192,0.18)', border: '#1565c0' }},
    {{ bg: 'rgba(69,39,160,0.18)', border: '#4527a0' }},
    {{ bg: 'rgba(0,96,100,0.18)', border: '#006064' }},
    {{ bg: 'rgba(136,14,79,0.18)', border: '#880e4f' }},
  ];

  for (let i = 0; i < data.length; i++) {{
    const c = data[i];
    const canvas = document.getElementById('radar_' + i);
    if (!canvas) continue;
    const color = colors[i % colors.length];
    new Chart(canvas, {{
      type: 'radar',
      data: {{
        labels: labels,
        datasets: [{{
          label: c.name,
          data: labels.map(l => c.dimensions[l] || 0),
          backgroundColor: color.bg,
          borderColor: color.border,
          borderWidth: 2.5,
          pointBackgroundColor: color.border,
          pointRadius: 4,
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: true,
        plugins: {{
          title: {{ display: true, text: c.name + ' (' + c.total + '分)', font: {{ size: 14, weight: 'bold' }} }}
        }},
        scales: {{
          r: {{
            beginAtZero: true,
            max: 100,
            ticks: {{ stepSize: 20, backdropColor: 'transparent' }},
            pointLabels: {{ font: {{ size: 11 }} }}
          }}
        }}
      }}
    }});
  }}
}}

// ===== 页面加载 =====
window.addEventListener('DOMContentLoaded', () => {{
  initLineChart();
  initRadarCharts();
  // 默认加载第一名候选人详情
  if (REPORT.competency.length > 0 && document.getElementById('candidateSelect')) {{
    document.getElementById('candidateSelect').value = REPORT.competency[0].name;
    renderDetail();
  }}
}});
</script>
</body>
</html>
"""


# ============================================================
# 3. 公开入口
# ============================================================

def generate_html_report(all_results, config, output_path):
    """
    从阅卷结果生成一份自包含的 HTML 可视化报告。

    Args:
        all_results: 候选人阅卷结果列表
        config:      打分标准配置（含 questions 列表）
        output_path: 输出 .html 文件路径
    """
    if not all_results:
        print("⚠️ 没有候选人数据，跳过 HTML 报告生成。")
        return

    # --- 数据计算 ---
    stats = _compute_question_stats(all_results, config)
    groups = _derive_competency_groups(config)
    comp_scores = _compute_competency_scores(all_results, groups)

    # --- 拼装 HTML ---
    html_parts = []
    html_parts.append(_build_head())
    html_parts.append(_build_header(all_results, config))
    html_parts.append(_build_overview_section(stats))
    html_parts.append(_build_ranking_table(all_results))
    html_parts.append(_build_candidate_detail_section(all_results))
    html_parts.append(_build_competency_section(comp_scores, list(groups.keys())))
    html_parts.append(_build_scripts(all_results, config, stats, comp_scores))

    full_html = "\n".join(html_parts)

    # --- 写入文件 ---
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"✅ HTML 报告已生成: {output_path}")


# ============================================================
# 辅助
# ============================================================

def _esc(text):
    """最短的 HTML 实体转义（用于服务端安全嵌入属性值 / <option>）。"""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
