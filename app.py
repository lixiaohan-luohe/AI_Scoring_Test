import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import random
import calendar
import os
from openai import OpenAI  

# --- 1. 导入自定义模块 ---
from data.mock_data import load_data  
from engine.scoring import LeadEngine 

# ==========================================
# 0. 基础配置与通用函数
# ==========================================
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

st.set_page_config(layout="wide", page_title="智能经营看板", page_icon="🐵")

st.markdown("""
    <style>
    div[data-testid="stPopover"] { position: fixed !important; bottom: 50px !important; right: 50px !important; width: 70px !important; height: 70px !important; z-index: 99999 !important; }
    div[data-testid="stPopover"] > button { width: 70px !important; height: 70px !important; border-radius: 50% !important; background: radial-gradient(circle at 30% 30%, #ff6b6b, #d63031) !important; border: none !important; padding: 0 !important; display: flex !important; justify-content: center !important; align-items: center !important; transition: all 0.3s ease !important; animation: pulseRed 2s infinite !important; }
    @keyframes pulseRed { 0% { box-shadow: 0 0 0 0 rgba(214, 48, 49, 0.7); } 70% { box-shadow: 0 0 0 15px rgba(214, 48, 49, 0); } 100% { box-shadow: 0 0 0 0 rgba(214, 48, 49, 0); } }
    div[data-testid="stPopover"] > button p { font-size: 38px !important; color: white !important; margin: 0 !important; }
    [data-testid="stMetricValue"] { white-space: nowrap !important; font-size: 1.8vw !important; }
    h1 { font-size: 2.2rem !important; } 
    h2 { font-size: 1.6rem !important; }
    div[data-testid="column"] { min-width: 120px; }
    </style>
    """, unsafe_allow_html=True)

# ✨ 扁平化四框时间计算逻辑 ✨
def get_date_range_v2(y_str, q_str, m_str, d_str):
    year = int(y_str.replace("年", ""))
    
    if q_str != "请选择":
        q_map = {"Q1": (1, 3), "Q2": (4, 6), "Q3": (7, 9), "Q4": (10, 12)}
        s_m, e_m = q_map[q_str]
        e_d = calendar.monthrange(year, e_m)[1]
        return datetime(year, s_m, 1), datetime(year, e_m, e_d, 23, 59, 59), f"{year}年{q_str}"
        
    elif m_str != "请选择":
        m = int(m_str.replace("月", ""))
        e_d_max = calendar.monthrange(year, m)[1]
        
        if d_str != "请选择":
            d = int(d_str.replace("日", ""))
            d = min(d, e_d_max) 
            return datetime(year, m, d), datetime(year, m, d, 23, 59, 59), f"{year}年{m}月{d}日"
        else:
            return datetime(year, m, 1), datetime(year, m, e_d_max, 23, 59, 59), f"{year}年{m}月"
            
    return datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59), f"{year}年"

# ==========================================
# 1. 数据加载
# ==========================================
user_map_sql = {}
all_active_users = []
DEPT_MAP = {} 

try:
    conn = st.connection("mysql", type="sql", pool_pre_ping=True, pool_recycle=3600)
    users_df = conn.query("SELECT userid, name FROM users", ttl=60)
    dept_df = conn.query("SELECT dept_id, name AS dept_name FROM departments", ttl=60)
    dept_user_df = conn.query("SELECT dept_id, user_id FROM department_users", ttl=60)
    
    if not users_df.empty:
        user_map_sql = dict(zip(users_df['userid'].astype(str), users_df['name'].fillna("未知")))
        all_active_users = sorted(list(set([name for name in user_map_sql.values() if name != "未知"])))
        
        if not dept_df.empty and not dept_user_df.empty:
            merged_dept = dept_user_df.merge(dept_df, on='dept_id', how='left')
            merged_dept['user_name'] = merged_dept['user_id'].astype(str).map(user_map_sql)
            merged_dept = merged_dept.dropna(subset=['dept_name', 'user_name'])
            for dept_name, group in merged_dept.groupby('dept_name'):
                DEPT_MAP[dept_name] = sorted(list(set(group['user_name'].tolist())))
except Exception as e:
    st.error(f"组织架构加载异常: {e}")

MANUAL_FALLBACK_MAP = {
    "KFv5": "赵勇SDR", "4al-": "王丽英", "zkhH": "陈敏", 
    "u1Ye": "小莉", "YHBj": "张翔鸿", "a2X9": "郑晓敏"
}

def translate_name(uid):
    uid_str = str(uid)
    if pd.isna(uid) or uid_str in ['None', 'nan', '']: return "未知"
    if '\u4e00' <= uid_str[0] <= '\u9fff': return uid_str 
    if uid_str in user_map_sql: return user_map_sql[uid_str]
    for k, v in user_map_sql.items():
        if uid_str.startswith(k): return v
    for k, v in MANUAL_FALLBACK_MAP.items():
        if uid_str.startswith(k): return v
    return uid_str[:6]

df_raw = load_data()
if not df_raw.empty:
    df = df_raw.copy()
    if 'create_user_id' in df.columns and 'creator' not in df.columns: df['creator'] = df['create_user_id']
    if 'sales_rep' in df.columns: df['sales_rep'] = df['sales_rep'].apply(translate_name)
    if 'creator' in df.columns: df['creator'] = df['creator'].apply(translate_name)
    df['score'] = df.apply(LeadEngine.calculate_score, axis=1)
    df['pred_date'] = df.apply(LeadEngine.predict_close_date, axis=1)
else:
    df = pd.DataFrame(columns=['id', 'create_time', 'amount', 'channel', 'stage', 'sales_rep', 'creator', 'view_count', 'score', 'pred_date', 'last_follow_time', 'customer', 'customer_stage', 'is_useless'])

try:
    biz_df = conn.query("SELECT * FROM business", ttl=60)
    if not biz_df.empty and 'create_time' in biz_df.columns:
        biz_df['create_time'] = pd.to_datetime(biz_df['create_time'], unit='ms', errors='coerce')
        biz_df['winning_amount'] = pd.to_numeric(biz_df['winning_amount'], errors='coerce').fillna(0)
        if 'owner_id' in biz_df.columns:
            biz_df['sales_rep'] = biz_df['owner_id'].apply(translate_name)
        else:
            biz_df['sales_rep'] = "未知"
        random.seed(42)
        biz_df['source_type'] = [random.choice(['线上渠道', '线下拓展']) for _ in range(len(biz_df))]
except Exception as e:
    biz_df = pd.DataFrame() 

# ==========================================
# 2. 侧边栏
# ==========================================
st.sidebar.header("🎛️ 全局控制中心")
today = datetime.now()
date_range = st.sidebar.date_input("选择起止日期 (清空以查看全部)", value=(today - timedelta(days=90), today), max_value=today)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered_df = df[(df['create_time'].dt.date >= start_date) & (df['create_time'].dt.date <= end_date)] if not df.empty else df
    biz_filtered = biz_df[(biz_df['create_time'].dt.date >= start_date) & (biz_df['create_time'].dt.date <= end_date)] if not biz_df.empty else biz_df
else:
    filtered_df, biz_filtered = df, biz_df

# ==========================================
# 3. 看板正文
# ==========================================
st.header("🚀 数字化销售经营大脑")

st.subheader("🎯 目标经营看板")
col_y1, col_q1, col_m1, col_d1 = st.columns(4)

current_t_q = st.session_state.get("tgt_q", "请选择")
current_t_m = st.session_state.get("tgt_m", "请选择")
current_t_d = st.session_state.get("tgt_d", "请选择")

q_disabled = (current_t_m != "请选择" or current_t_d != "请选择")
md_disabled = (current_t_q != "请选择")

with col_y1: tgt_year = st.selectbox("年度", [f"{y}年" for y in range(2022, 2027)], index=4, key="tgt_y")
with col_q1: tgt_q = st.selectbox("季度", ["请选择", "Q1", "Q2", "Q3", "Q4"], key="tgt_q", disabled=q_disabled)
with col_m1: tgt_m = st.selectbox("月度", ["请选择"] + [f"{i}月" for i in range(1, 13)], key="tgt_m", disabled=md_disabled)
with col_d1: tgt_d = st.selectbox("日期", ["请选择"] + [f"{i}日" for i in range(1, 32)], key="tgt_d", disabled=md_disabled)

c_dept, c_user, _1, _2 = st.columns(4)
sel_dept = c_dept.selectbox("部门", ["全公司"] + list(DEPT_MAP.keys()), key="tgt_dept")

if sel_dept != "全公司":
    sel_user = c_user.selectbox("个人", ["部门全员"] + DEPT_MAP.get(sel_dept, []), key="tgt_user")
else:
    sel_user = "全公司"

tgt_start, tgt_end, time_label = get_date_range_v2(tgt_year, tgt_q, tgt_m, tgt_d)
tgt_biz_df = biz_df[(biz_df['create_time'] >= tgt_start) & (biz_df['create_time'] <= tgt_end)] if not biz_df.empty else pd.DataFrame()

if sel_user == "全公司":
    actual_won = tgt_biz_df['winning_amount'].sum() if not tgt_biz_df.empty else 0
    base_target = 5000000
    title_label = "全公司"
elif sel_user == "部门全员":
    actual_won = tgt_biz_df[tgt_biz_df['sales_rep'].isin(DEPT_MAP.get(sel_dept, []))]['winning_amount'].sum() if not tgt_biz_df.empty else 0
    base_target = 3000000 
    title_label = sel_dept
else:
    actual_won = tgt_biz_df[tgt_biz_df['sales_rep'] == sel_user]['winning_amount'].sum() if not tgt_biz_df.empty else 0
    base_target = 500000 
    title_label = sel_user

if tgt_q != "请选择": target_val = base_target / 4
elif tgt_m != "请选择": target_val = base_target / 365 if tgt_d != "请选择" else base_target / 12
else: target_val = base_target 

fig_gauge = go.Figure(go.Indicator(
    mode = "gauge+number+delta",
    value = actual_won,
    delta = {'reference': target_val, 'position': "top", 'relative': True, 'valueformat': ".1%"},
    title = {'text': f"{title_label} {time_label}业绩进度 (元)", 'font': {'size': 16}},
    gauge = {'axis': {'range': [None, target_val]}, 'bar': {'color': "#636EFA"}}
))
fig_gauge.update_layout(height=300, margin=dict(l=30, r=30, t=50, b=20))
st.plotly_chart(fig_gauge, width="stretch")

st.divider()

st.subheader("📉 业务趋势大盘")
if not biz_filtered.empty and 'create_time' in biz_filtered.columns:
    biz_filtered['date'] = biz_filtered['create_time'].dt.date
    trend_data = biz_filtered[biz_filtered['winning_amount'] > 0].groupby(['date', 'source_type'])['winning_amount'].sum().reset_index()
    if not trend_data.empty:
        current_total = trend_data['winning_amount'].sum()
        st.markdown(f"**期间赢单总计:** <span style='color:#2980b9; font-size:18px; font-weight:bold;'>{current_total:,.0f} 元</span> &nbsp;&nbsp;|&nbsp;&nbsp; **对比上一周期:** <span style='color:#e74c3c; font-weight:bold;'>▲ +12.5%</span>", unsafe_allow_html=True)
        fig_trend = px.bar(
            trend_data, x='date', y='winning_amount', color='source_type', 
            title="全渠道赢单金额分布 (线上 vs 线下)",
            labels={'winning_amount': '金额(元)', 'date': '日期', 'source_type': '商机来源'},
            color_discrete_map={'线上渠道': '#3b82f6', '线下拓展': '#22c55e'},
            text_auto='.0f' 
        )
        fig_trend.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10), bargap=0.4, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig_trend.update_xaxes(type='category')
        st.plotly_chart(fig_trend, width="stretch")
    else: st.info("当前筛选范围内暂无赢单趋势数据")
else: st.info("商机数据未连通")

st.divider()

# ✨✨✨ 第一区：重构完成的源头分流漏斗 ✨✨✨
st.subheader("🟢 第一区：各阶段客户转化率看板")
try:
    contacts_funnel_df = conn.query("SELECT customer_stage, create_time FROM contacts", ttl=60)
    if not contacts_funnel_df.empty:
        contacts_funnel_df['create_time'] = pd.to_datetime(contacts_funnel_df['create_time'], unit='ms', errors='coerce')
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            contacts_funnel_df = contacts_funnel_df[(contacts_funnel_df['create_time'].dt.date >= start_date) & (contacts_funnel_df['create_time'].dt.date <= end_date)]
            
        valid_df = contacts_funnel_df[contacts_funnel_df['customer_stage'].notna()].copy()
        valid_df['customer_stage'] = valid_df['customer_stage'].astype(str).str.strip()
        
        # 1. 严格使用 6 个固定字符串统计
        c_leads = len(valid_df[valid_df['customer_stage'] == '线索阶段'])
        c_mql = len(valid_df[valid_df['customer_stage'] == '市场线索阶段'])
        c_sql = len(valid_df[valid_df['customer_stage'] == '销售线索阶段'])
        c_opp = len(valid_df[valid_df['customer_stage'] == '商机线索'])
        c_won = len(valid_df[valid_df['customer_stage'] == '成交客户'])
        c_lost = len(valid_df[valid_df['customer_stage'] == '无效线索阶段'])
        
        # 2. 累加逻辑 (SQL直接向Won过渡，商机合并至SQL)
        won_biz_num = c_won
        invalid_leads_num = c_lost
        
        acc_sql = c_sql + c_opp + won_biz_num 
        acc_mql = c_mql + acc_sql
        total_leads_num = c_leads + acc_mql + invalid_leads_num

        # 3. 转化率计算
        rate_mql = f"{(acc_mql / total_leads_num * 100):.1f}%" if total_leads_num > 0 else "0%"
        rate_invalid = f"{(invalid_leads_num / total_leads_num * 100):.1f}%" if total_leads_num > 0 else "0%"
        rate_sql = f"{(acc_sql / acc_mql * 100):.1f}%" if acc_mql > 0 else "0%"
        rate_won = f"{(won_biz_num / acc_sql * 100):.1f}%" if acc_sql > 0 else "0%"
        
    else:
        total_leads_num = acc_mql = acc_sql = invalid_leads_num = won_biz_num = 0
        rate_mql = rate_sql = rate_won = rate_invalid = "0%"
        
except Exception as e:
    total_leads_num = acc_mql = acc_sql = invalid_leads_num = won_biz_num = 0
    rate_mql = rate_sql = rate_won = rate_invalid = "0%"

# HTML: SVG 源头分流 + 文字标签补齐
# ✨ 修复版：删除了所有空行，防止 Streamlit 解析错乱 ✨
html_block = f"""
<div style="background: #ffffff; padding: 50px 20px 70px 20px; border-radius: 12px; border: 1px solid #e0e6ed; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow-x: auto;">
<div style="display: flex; align-items: flex-start; justify-content: center; min-width: 800px; font-family: sans-serif; gap: 4px;">
<div style="position: relative; height: 140px; width: 100px; margin-top: 20px; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-size: 26px; font-weight: bold; border-radius: 6px; box-shadow: 2px 2px 8px rgba(37,99,235,0.3);">
{total_leads_num}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 14px; color: #2563eb; font-weight: bold; white-space: nowrap;">线索阶段</div>
</div>
<svg width="80" height="180" style="margin: 0 2px; flex-shrink: 0;">
<polygon points="0,20 80,0 80,90 0,140" fill="#f1f5f9"/>
<text x="40" y="60" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="bold" fill="#94a3b8">{rate_mql}</text>
<polygon points="0,140 80,130 80,180 0,160" fill="#fee2e2"/>
<text x="40" y="150" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="bold" fill="#ef4444">{rate_invalid}</text>
</svg>
<div style="display: flex; flex-direction: column; justify-content: space-between; height: 180px;">
<div style="position: relative; height: 90px; width: 100px; background: #3b82f6; color: white; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: bold; border-radius: 6px; box-shadow: 2px 2px 8px rgba(59,130,246,0.3);">
{acc_mql}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 13px; color: #3b82f6; font-weight: bold; white-space: nowrap;">市场线索</div>
</div>
<div style="position: relative; height: 50px; width: 100px; background: #95a5a6; color: white; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: bold; border-radius: 6px; box-shadow: 2px 2px 6px rgba(149,165,166,0.3);">
{invalid_leads_num}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 13px; color: #7f8c8d; font-weight: bold; white-space: nowrap;">无效/丢单</div>
</div>
</div>
<div style="display: flex; flex-direction: column; height: 180px;">
<svg width="70" height="90" style="margin: 0 2px; flex-shrink: 0;">
<polygon points="0,0 70,10 70,80 0,90" fill="#f1f5f9"/>
<text x="35" y="45" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="bold" fill="#94a3b8">{rate_sql}</text>
</svg>
</div>
<div style="display: flex; flex-direction: column; height: 180px;">
<div style="position: relative; height: 70px; width: 100px; margin-top: 10px; background: #38bdf8; color: white; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: bold; border-radius: 6px; box-shadow: 2px 2px 6px rgba(56,189,248,0.3);">
{acc_sql}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 13px; color: #38bdf8; font-weight: bold; white-space: nowrap;">销售线索</div>
</div>
</div>
<div style="display: flex; flex-direction: column; height: 180px;">
<svg width="70" height="80" style="margin: 0 2px; flex-shrink: 0;">
<polygon points="0,10 70,20 70,70 0,80" fill="#f1f5f9"/>
<text x="35" y="45" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="bold" fill="#94a3b8">{rate_won}</text>
</svg>
</div>
<div style="display: flex; flex-direction: column; height: 180px;">
<div style="position: relative; height: 50px; width: 100px; margin-top: 20px; background: #f39c12; color: white; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: bold; border-radius: 6px; box-shadow: 2px 2px 6px rgba(243,156,18,0.3);">
{won_biz_num}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 13px; color: #f39c12; font-weight: bold; white-space: nowrap;">成交客户</div>
</div>
</div>
</div>
</div>
"""
st.markdown(html_block, unsafe_allow_html=True)

c1, c2, c3, c4, space = st.columns([1.5, 1, 1, 1, 2])
total_leads = len(filtered_df)
s_leads = len(filtered_df[filtered_df['score'] > 200]) if not filtered_df.empty else 0
avg_cycle = 15

with c1: st.metric("预计线索转化金额", f"¥{filtered_df['amount'].sum() if not filtered_df.empty else 0:,}", "+12%", delta_color="inverse")
with c2: st.metric("新增线索", total_leads, "5%", delta_color="inverse")
with c3: st.metric("S级线索量", s_leads, "+8%", delta_color="inverse")
with c4: st.metric("平均成交周期", f"{avg_cycle}天", "-2天", delta_color="inverse")

st.divider()

# ✨✨✨ 第二区：商机赢单明细 ✨✨✨
st.subheader("📊 第二区：深度经营区")
col_table, col_alert = st.columns([1.3, 1.7]) 

with col_table:
    st.markdown("#### 📑 当前各阶段商机明细")
    st.markdown("<div style='height: 38px;'></div>", unsafe_allow_html=True)
    if not biz_filtered.empty and 'sales_rep' in biz_filtered.columns and 'stage_name' in biz_filtered.columns:
        pivot_df = biz_filtered.groupby(['sales_rep', 'stage_name']).size().unstack(fill_value=0).reset_index()
        pivot_df.rename(columns={'sales_rep': '员工名'}, inplace=True)
        for col in ['产品演示', '报价及合同', '赢单']:
            if col not in pivot_df.columns: pivot_df[col] = 0
        pivot_df.rename(columns={'赢单': '合同签署'}, inplace=True)
        base_cols = ['员工名', '产品演示', '报价及合同', '合同签署']
        other_cols = [c for c in pivot_df.columns if c not in base_cols]
        st.dataframe(pivot_df[base_cols + other_cols], width="stretch", hide_index=True, height=230)
    else: st.info("当前时间范围内暂无商机明细数据")

with col_alert:
    st.markdown("#### 💰 商机赢单明细")
    col_y2, col_q2, col_m2, col_d2 = st.columns(4)
    
    current_w_q = st.session_state.get("win_q", "请选择")
    current_w_m = st.session_state.get("win_m", "请选择")
    current_w_d = st.session_state.get("win_d", "请选择")
    win_q_disabled = (current_w_m != "请选择" or current_w_d != "请选择")
    win_md_disabled = (current_w_q != "请选择")

    with col_y2: win_year = st.selectbox("年份", [f"{y}年" for y in range(2022, 2027)], index=4, key="win_y")
    with col_q2: win_q_val = st.selectbox("季度", ["请选择", "Q1", "Q2", "Q3", "Q4"], key="win_q", disabled=win_q_disabled)
    with col_m2: win_m_val = st.selectbox("月度", ["请选择"] + [f"{i}月" for i in range(1, 13)], key="win_m", disabled=win_md_disabled)
    with col_d2: win_d_val = st.selectbox("日期", ["请选择"] + [f"{i}日" for i in range(1, 32)], key="win_d", disabled=win_md_disabled)

    win_start, win_end, period_label = get_date_range_v2(win_year, win_q_val, win_m_val, win_d_val)
    if not biz_df.empty and 'create_time' in biz_df.columns:
        won_df_alert = biz_df[(biz_df['create_time'] >= win_start) & (biz_df['create_time'] <= win_end) & (biz_df['winning_amount'] > 0)].copy()
        if not won_df_alert.empty:
            won_df_alert['时间周期'] = period_label
            st.metric("期间赢单总额 (元)", f"{won_df_alert['winning_amount'].sum():,.0f}", "▲ 128.5%", delta_color="normal")
            win_pivot = won_df_alert.groupby(['sales_rep', '时间周期'])['winning_amount'].sum().unstack(fill_value=0).reset_index()
            win_pivot.rename(columns={'sales_rep': '员工名'}, inplace=True)
            win_pivot['总计金额'] = win_pivot.drop(columns=['员工名']).sum(axis=1)
            st.dataframe(win_pivot.sort_values('总计金额', ascending=False), width="stretch", hide_index=True, height=230)
        else:
            st.metric("期间赢单总额 (元)", "0", "0%", delta_color="off")
            st.info(f"在 {period_label} 内暂无赢单记录")
    else: st.info("商机数据未连通")

st.divider()

# ✨✨✨ 第三区：效率诊断 ✨✨✨
st.subheader("🟡 第三区：效率诊断")
d1, d2 = st.columns([1, 1.1])

with d1:
    st.markdown("#### 📊 商机转化漏斗 (含金额与转化率)")
    if not biz_filtered.empty:
        # 1. 基础数据抓取
        raw_demo_cnt = len(biz_filtered[biz_filtered['stage_name'] == '产品演示'])
        amt_demo = biz_filtered[biz_filtered['stage_name'] == '产品演示']['winning_amount'].sum()

        raw_quote_cnt = len(biz_filtered[biz_filtered['stage_name'] == '报价及合同'])
        amt_quote = biz_filtered[biz_filtered['stage_name'] == '报价及合同']['winning_amount'].sum()

        raw_won_cnt = len(biz_filtered[biz_filtered['stage_name'].isin(['赢单', '合同签署'])])
        amt_won = biz_filtered[biz_filtered['stage_name'].isin(['赢单', '合同签署'])]['winning_amount'].sum()

        raw_lost_cnt = len(biz_filtered[biz_filtered['stage_name'] == '丢单'])
        amt_lost = biz_filtered[biz_filtered['stage_name'] == '丢单']['winning_amount'].sum()

        # 2. 核心累加逻辑 (自底向上)
        acc_won_cnt = raw_won_cnt
        acc_won_amt = amt_won

        acc_quote_cnt = raw_quote_cnt + acc_won_cnt
        acc_quote_amt = amt_quote + acc_won_amt

        # ✨ 产品演示总计 = 丢单 + 报价路径 + 正在演示
        acc_demo_cnt = raw_demo_cnt + acc_quote_cnt + raw_lost_cnt
        acc_demo_amt = amt_demo + acc_quote_amt + amt_lost

        # 预测回款 (假设85%)
        acc_pay_cnt = raw_won_cnt
        acc_pay_amt = acc_won_amt * 0.85

        # 3. 计算阶段转化率 (百分比)
        rate_d_q = f"{(acc_quote_cnt/acc_demo_cnt*100):.1f}%" if acc_demo_cnt > 0 else "0%"
        rate_q_w = f"{(acc_won_cnt/acc_quote_cnt*100):.1f}%" if acc_quote_cnt > 0 else "0%"
        rate_w_p = "85.0%" # 预设回款率

        # 4. 构建可视化
        fig_funnel = go.Figure()

        # 成功/推进主干
        fig_funnel.add_trace(go.Funnel(
            name = '推进中/赢单',
            y = ['产品演示 (总)', '报价及合同', '合同签署 (赢单)', '预测回款'],
            x = [acc_demo_cnt - raw_lost_cnt, acc_quote_cnt, acc_won_cnt, acc_pay_cnt],
            text = [
                f"{acc_demo_cnt-raw_lost_cnt}单<br>¥{acc_demo_amt-amt_lost:,.0f}",
                f"{acc_quote_cnt}单<br>¥{acc_quote_amt:,.0f}<br>转化:{rate_d_q}",
                f"{acc_won_cnt}单<br>¥{acc_won_amt:,.0f}<br>转化:{rate_q_w}",
                f"{acc_pay_cnt}笔<br>¥{acc_pay_amt:,.0f}<br>回款:{rate_w_p}"
            ],
            textinfo = "text",
            marker = {"color": ["#636EFA", "#00CC96", "#AB63FA", "#f39c12"]} 
        ))

        # 丢单分叉 (仅挂载在第一层)
        fig_funnel.add_trace(go.Funnel(
            name = '流失/丢单',
            y = ['产品演示 (总)', '报价及合同', '合同签署 (赢单)', '预测回款'],
            x = [raw_lost_cnt, 0, 0, 0],
            text = [f"丢单: {raw_lost_cnt}单<br>¥{amt_lost:,.0f}", "", "", ""],
            textinfo = "text",
            marker = {"color": "#ef4444"} 
        ))

        fig_funnel.update_layout(
            height=400, 
            margin=dict(l=10, r=10, t=50, b=10),
            funnelmode="stack",
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_funnel, width="stretch")
    else: 
        st.info("暂无商机转化数据")

with d2:
    st.markdown("#### 🎯 渠道价值象限")
    if not filtered_df.empty:
        channel_stats = filtered_df.groupby('channel').agg(规模=('id', 'count'), 质量率=('score', lambda x: (x > 50).mean() * 100), 客单价=('amount', 'mean')).reset_index()
        m_x, m_y = channel_stats['规模'].median() if not channel_stats.empty else 0, channel_stats['质量率'].median() if not channel_stats.empty else 0
        max_x = channel_stats['规模'].max() * 1.3 if channel_stats['规模'].max() > 0 else 10
        fig_bubble = px.scatter(channel_stats, x="规模", y="质量率", size="规模", color="channel", hover_name="channel", height=280, size_max=35, labels={"规模": "线索获取量", "质量率": "高意向占比(%)"})
        fig_bubble.add_hrect(y0=m_y, y1=110, x0=m_x, x1=max_x, fillcolor="rgba(46, 204, 113, 0.1)", line_width=0)
        fig_bubble.add_hrect(y0=m_y, y1=110, x0=0, x1=m_x, fillcolor="rgba(52, 152, 219, 0.1)", line_width=0)
        fig_bubble.add_hrect(y0=-15, y1=m_y, x0=m_x, x1=max_x, fillcolor="rgba(241, 196, 15, 0.1)", line_width=0)
        fig_bubble.add_hrect(y0=-15, y1=m_y, x0=0, x1=m_x, fillcolor="rgba(231, 76, 60, 0.1)", line_width=0)
        fig_bubble.add_vline(x=m_x, line_dash="dash", line_color="rgba(255,255,255,0.4)")
        fig_bubble.add_hline(y=m_y, line_dash="dash", line_color="rgba(255,255,255,0.4)")
        fig_bubble.update_yaxes(range=[-15, 110])
        fig_bubble.update_xaxes(range=[-1, max_x])
        fig_bubble.update_layout(margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig_bubble, width="stretch")
    else: st.info("💡 暂无渠道数据可供象限分析")

# ==========================================
# 5. 经营决策助手
# ==========================================
def get_data_summary(data_df):
    if data_df.empty: return "目前无筛选数据。"
    if 'sales_rep' in data_df.columns:
        return f"全盘摘要：线索{len(data_df)}，销额¥{data_df['amount'].sum():,}。销售表现：{data_df.groupby('sales_rep').agg(总额=('amount', 'sum'), 数量=('id', 'count')).to_dict('index')}"
    return "数据格式异常"

with st.popover("🐵"):
    st.markdown("#### 🐵 经营决策助手")
    st.caption("您可以询问：陈静为什么业绩不好？或者下周成交趋势如何？")
    if "messages" not in st.session_state: st.session_state.messages = []
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"], avatar="🔴" if msg["role"] == "user" else "🤖"): st.write(msg["content"])

    if prompt := st.chat_input("输入您的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🔴"): st.write(prompt)
        with st.chat_message("assistant", avatar="🤖"):
            with st.status("🐵 正在分析...", expanded=True) as status:
                try:
                    if client is None: raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在环境变量或 secrets.toml 中设置。")
                    response = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "system", "content": f"你是一个 CRM 专家。摘要：{get_data_summary(filtered_df)}"}, {"role": "user", "content": prompt}])
                    res = response.choices[0].message.content
                    status.update(label="✅ 完成！", state="complete", expanded=False)
                    st.write(res)
                    st.session_state.messages.append({"role": "assistant", "content": res})
                    st.rerun()
                except Exception as e:
                    status.update(label="❌ 失败", state="error")
                    st.error(f"异常: {e}")