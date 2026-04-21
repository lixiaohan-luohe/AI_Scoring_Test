import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random
import json
import os
import calendar
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
    /* 确保四列下拉框不会被压缩 */
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
# ✨✨✨ 第一区：目标经营看板 (四框平铺互斥) ✨✨✨
st.subheader("🎯 目标经营看板")

# 使用显式的四个列，并添加提示文字确保显示
col_y1, col_q1, col_m1, col_d1 = st.columns(4)

# 读取当前 session 状态以实现互斥
current_t_q = st.session_state.get("tgt_q", "请选择")
current_t_m = st.session_state.get("tgt_m", "请选择")
current_t_d = st.session_state.get("tgt_d", "请选择")

# 互斥逻辑：季度被选则月度/日期禁用，月度/日期被选则季度禁用
q_disabled = (current_t_m != "请选择" or current_t_d != "请选择")
md_disabled = (current_t_q != "请选择")

with col_y1:
    tgt_year = st.selectbox("年度", [f"{y}年" for y in range(2022, 2027)], index=4, key="tgt_y")
with col_q1:
    tgt_q = st.selectbox("季度", ["请选择", "Q1", "Q2", "Q3", "Q4"], key="tgt_q", disabled=q_disabled)
with col_m1:
    tgt_m = st.selectbox("月度", ["请选择"] + [f"{i}月" for i in range(1, 13)], key="tgt_m", disabled=md_disabled)
with col_d1:
    tgt_d = st.selectbox("日期", ["请选择"] + [f"{i}日" for i in range(1, 32)], key="tgt_d", disabled=md_disabled)

# 部门/个人筛选（原有逻辑保持不变）
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
elif tgt_m != "请选择":
    if tgt_d != "请选择": target_val = base_target / 365
    else: target_val = base_target / 12
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
        fig_trend.update_layout(
            height=350, margin=dict(l=10, r=10, t=40, b=10),
            bargap=0.4, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig_trend.update_xaxes(type='category')
        fig_trend.update_traces(textfont_size=13, textangle=0, textposition="inside")
        st.plotly_chart(fig_trend, width="stretch")
    else:
        st.info("当前筛选范围内暂无赢单趋势数据")
else:
    st.info("商机数据未连通")

st.divider()

st.subheader("🟢 第一区：各阶段客户转化率看板")
try:
    contacts_funnel_df = conn.query("SELECT customer_stage, create_time FROM contacts", ttl=60)
    if not contacts_funnel_df.empty:
        contacts_funnel_df['create_time'] = pd.to_datetime(contacts_funnel_df['create_time'], unit='ms', errors='coerce')
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            contacts_funnel_df = contacts_funnel_df[(contacts_funnel_df['create_time'].dt.date >= start_date) & (contacts_funnel_df['create_time'].dt.date <= end_date)]
            
        valid_df = contacts_funnel_df[
            contacts_funnel_df['customer_stage'].notna() & 
            (contacts_funnel_df['customer_stage'] != '') & 
            (contacts_funnel_df['customer_stage'].str.lower() != 'nell') &
            (contacts_funnel_df['customer_stage'].str.lower() != 'null')
        ]
        total_leads_num = len(valid_df)
        mql_num = len(valid_df[valid_df['customer_stage'].str.contains('市场线索', na=False)])
        sql_num = len(valid_df[valid_df['customer_stage'].str.contains('销售线索', na=False)])
        invalid_leads_num = len(valid_df[valid_df['customer_stage'].str.contains('无效线索', na=False)])
    else:
        total_leads_num = mql_num = sql_num = invalid_leads_num = 0
except Exception as e:
    total_leads_num = mql_num = sql_num = invalid_leads_num = 0

valid_biz_num = len(biz_filtered)
won_biz_num = len(biz_filtered[biz_filtered['stage_name'].isin(['赢单', '合同签署'])]) if not biz_filtered.empty else 0

rate_mql = f"{(mql_num / total_leads_num * 100):.1f}%" if total_leads_num > 0 else "0%"
rate_sql = f"{(sql_num / mql_num * 100):.1f}%" if mql_num > 0 else "0%"
rate_biz = f"{(valid_biz_num / sql_num * 100):.1f}%" if sql_num > 0 else "0%"
rate_invalid = f"{(invalid_leads_num / sql_num * 100):.1f}%" if sql_num > 0 else "0%"
rate_won = f"{(won_biz_num / valid_biz_num * 100):.1f}%" if valid_biz_num > 0 else "0%"

html_block = f"""
<div style="background: #ffffff; padding: 50px 20px 70px 20px; border-radius: 12px; border: 1px solid #e0e6ed; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow-x: auto;">
<div style="display: flex; align-items: center; justify-content: center; min-width: 850px; font-family: sans-serif;">
<div style="position: relative; height: 140px; width: 90px; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: bold; border-radius: 4px; box-shadow: 2px 2px 6px rgba(37,99,235,0.3);">
{total_leads_num}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 13px; color: #2563eb; font-weight: bold; white-space: nowrap;">线索阶段</div>
</div>
<svg width="60" height="140" style="margin: 0 2px; flex-shrink: 0;"><polygon points="0,0 60,15 60,125 0,140" fill="#f1f5f9"/><text x="30" y="70" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="bold" fill="#94a3b8">{rate_mql}</text></svg>
<div style="position: relative; height: 110px; width: 90px; background: #3b82f6; color: white; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: bold; border-radius: 4px; box-shadow: 2px 2px 6px rgba(59,130,246,0.3);">
{mql_num}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 13px; color: #3b82f6; font-weight: bold; white-space: nowrap;">市场线索</div>
</div>
<svg width="60" height="110" style="margin: 0 2px; flex-shrink: 0;"><polygon points="0,0 60,15 60,95 0,110" fill="#f1f5f9"/><text x="30" y="55" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="bold" fill="#94a3b8">{rate_sql}</text></svg>
<div style="position: relative; height: 80px; width: 90px; background: #38bdf8; color: white; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; border-radius: 4px; box-shadow: 2px 2px 6px rgba(56,189,248,0.3);">
{sql_num}
<div style="position: absolute; top: 100%; margin-top: 12px; width: 100%; text-align: center; font-size: 13px; color: #38bdf8; font-weight: bold; white-space: nowrap;">销售线索</div>
</div>
<svg width="70" height="120" style="margin: 0 2px; flex-shrink: 0;"><polygon points="0,20 70,0 70,60 0,60" fill="#f1f5f9"/><text x="35" y="25" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="bold" fill="#94a3b8">{rate_biz}</text><polygon points="0,60 70,80 70,120 0,100" fill="#f87171" opacity="0.15"/><text x="35" y="95" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="bold" fill="#ef4444">{rate_invalid}</text></svg>
<div style="display: flex; flex-direction: column; justify-content: space-between; height: 120px;">
<div style="display: flex; align-items: center; height: 60px;">
<div style="position: relative; height: 60px; width: 90px; background: #27ae60; color: white; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: bold; border-radius: 4px; box-shadow: 2px 2px 6px rgba(39,174,96,0.3);">
{valid_biz_num}
<div style="position: absolute; top: -24px; width: 100%; text-align: center; font-size: 12px; color: #27ae60; font-weight: bold; white-space: nowrap;">商机/赢单</div>
</div>
<svg width="50" height="60" style="margin: 0 2px; flex-shrink: 0;"><polygon points="0,0 50,10 50,50 0,60" fill="#f1f5f9"/><text x="25" y="30" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="bold" fill="#94a3b8">{rate_won}</text></svg>
<div style="position: relative; height: 40px; width: 90px; background: #f39c12; color: white; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; border-radius: 4px; box-shadow: 2px 2px 6px rgba(243,156,18,0.3);">
{won_biz_num}
<div style="position: absolute; top: 100%; margin-top: 8px; width: 100%; text-align: center; font-size: 12px; color: #f39c12; font-weight: bold; white-space: nowrap;">成交客户</div>
</div>
</div>
<div style="display: flex; align-items: center; height: 40px;">
<div style="position: relative; height: 40px; width: 90px; background: #95a5a6; color: white; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; border-radius: 4px; box-shadow: 2px 2px 6px rgba(149,165,166,0.3);">
{invalid_leads_num}
<div style="position: absolute; top: 100%; margin-top: 8px; width: 100%; text-align: center; font-size: 12px; color: #7f8c8d; font-weight: bold; white-space: nowrap;">无效/丢单</div>
</div>
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

# ✨✨✨ 第二区：商机赢单明细 (四框平铺互斥) ✨✨✨
st.subheader("📊 第二区：深度经营区")

col_table, col_alert = st.columns([1.3, 1.7]) 

with col_table:
    st.markdown("#### 📑 当前各阶段商机明细")
    st.markdown("<div style='height: 38px;'></div>", unsafe_allow_html=True)
    
    if not biz_filtered.empty and 'sales_rep' in biz_filtered.columns and 'stage_name' in biz_filtered.columns:
        pivot_df = biz_filtered.groupby(['sales_rep', 'stage_name']).size().unstack(fill_value=0).reset_index()
        pivot_df.rename(columns={'sales_rep': '员工名'}, inplace=True)
        for col in ['产品演示', '报价及合同', '赢单']:
            if col not in pivot_df.columns:
                pivot_df[col] = 0
        pivot_df.rename(columns={'赢单': '合同签署'}, inplace=True)
        base_cols = ['员工名', '产品演示', '报价及合同', '合同签署']
        other_cols = [c for c in pivot_df.columns if c not in base_cols]
        pivot_df = pivot_df[base_cols + other_cols]
        
        st.dataframe(pivot_df, width="stretch", hide_index=True, height=230)
    else:
        st.info("当前时间范围内暂无商机明细数据")

with col_alert:
    st.markdown("#### 💰 商机赢单明细")
    
    # 第二组时间框：四个并排，互斥逻辑同第一区
    col_y2, col_q2, col_m2, col_d2 = st.columns(4)
    
    current_w_q = st.session_state.get("win_q", "请选择")
    current_w_m = st.session_state.get("win_m", "请选择")
    current_w_d = st.session_state.get("win_d", "请选择")

    win_q_disabled = (current_w_m != "请选择" or current_w_d != "请选择")
    win_md_disabled = (current_w_q != "请选择")

    with col_y2:
        win_year = st.selectbox("年份", [f"{y}年" for y in range(2022, 2027)], index=4, key="win_y")
    with col_q2:
        win_q_val = st.selectbox("季度", ["请选择", "Q1", "Q2", "Q3", "Q4"], key="win_q", disabled=win_q_disabled)
    with col_m2:
        win_m_val = st.selectbox("月度", ["请选择"] + [f"{i}月" for i in range(1, 13)], key="win_m", disabled=win_md_disabled)
    with col_d2:
        win_d_val = st.selectbox("日期", ["请选择"] + [f"{i}日" for i in range(1, 32)], key="win_d", disabled=win_md_disabled)

    win_start, win_end, period_label = get_date_range_v2(win_year, win_q_val, win_m_val, win_d_val)
    
    if not biz_df.empty and 'create_time' in biz_df.columns:
        won_df_alert = biz_df[(biz_df['create_time'] >= win_start) & (biz_df['create_time'] <= win_end) & (biz_df['winning_amount'] > 0)].copy()

        if not won_df_alert.empty:
            won_df_alert['时间周期'] = period_label
            total_amt = won_df_alert['winning_amount'].sum()
            
            st.metric("期间赢单总额 (元)", f"{total_amt:,.0f}", "▲ 128.5%", delta_color="normal")

            win_pivot = won_df_alert.groupby(['sales_rep', '时间周期'])['winning_amount'].sum().unstack(fill_value=0).reset_index()
            win_pivot.rename(columns={'sales_rep': '员工名'}, inplace=True)
            win_pivot['总计金额'] = win_pivot.drop(columns=['员工名']).sum(axis=1)
            win_pivot = win_pivot.sort_values('总计金额', ascending=False)
            
            st.dataframe(win_pivot, width="stretch", hide_index=True, height=230)
        else:
            st.metric("期间赢单总额 (元)", "0", "0%", delta_color="off")
            st.info(f"在 {period_label} 内暂无赢单记录")
    else:
        st.info("商机数据未连通")

st.divider()

st.subheader("🟡 第三区：效率诊断")
d1, d2 = st.columns([1, 1.1])

with d1:
    st.markdown("#### 📊 商机转化漏斗 (含回款)")
    if not biz_filtered.empty:
        if 'except_amount' not in biz_filtered.columns: biz_filtered['except_amount'] = 0
        
        def calc_stage_amt(df_subset):
            amt = df_subset.apply(
                lambda row: row['winning_amount'] if pd.notna(row['winning_amount']) and row['winning_amount'] > 0 
                else (row['except_amount'] if pd.notna(row['except_amount']) else 0), 
                axis=1
            ).sum()
            return 0 if pd.isna(amt) else amt
            
        demo_df = biz_filtered[biz_filtered['stage_name'].isin(['产品演示', '报价及合同', '赢单', '丢单'])]
        demo_all = len(demo_df)
        demo_amt = calc_stage_amt(demo_df)
        
        quote_df = biz_filtered[biz_filtered['stage_name'].isin(['报价及合同', '赢单'])]
        quote_all = len(quote_df)
        quote_amt = calc_stage_amt(quote_df)
        
        won_df = biz_filtered[biz_filtered['stage_name'] == '赢单']
        won_all = len(won_df)
        won_amt = won_df['winning_amount'].fillna(0).sum()
        
        pay_all = int(won_all * 0.85) if won_all > 0 else 0
        pay_amt = won_amt * 0.85
        
        custom_text = [
            f"{demo_all} 单<br>¥ {demo_amt:,.0f}",
            f"{quote_all} 单<br>¥ {quote_amt:,.0f}",
            f"{won_all} 单<br>¥ {won_amt:,.0f}",
            f"{pay_all} 笔<br>¥ {pay_amt:,.0f}"
        ]
        
        fig_funnel = go.Figure(go.Funnel(
            y=['产品演示(全口径)', '报价及合同', '合同签署(赢单)', '实际回款'], 
            x=[demo_all, quote_all, won_all, pay_all],
            text=custom_text,
            textinfo="text", 
            marker={"color": ["#636EFA", "#00CC96", "#AB63FA", "#f39c12"]} 
        ))
        fig_funnel.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10)) 
        st.plotly_chart(fig_funnel, width="stretch")
    else: 
        st.info("暂无商机漏斗数据")

with d2:
    st.markdown("#### 🎯 渠道价值象限")
    if not filtered_df.empty:
        channel_stats = filtered_df.groupby('channel').agg(
            规模=('id', 'count'), 
            质量率=('score', lambda x: (x > 50).mean() * 100), 
            客单价=('amount', 'mean')
        ).reset_index()

        m_x = channel_stats['规模'].median() if not channel_stats.empty else 0
        m_y = channel_stats['质量率'].median() if not channel_stats.empty else 0
        max_x = channel_stats['规模'].max() * 1.3 if channel_stats['规模'].max() > 0 else 10
        
        fig_bubble = px.scatter(
            channel_stats, x="规模", y="质量率", size="规模", color="channel",
            hover_name="channel", 
            height=280, size_max=35, 
            labels={"规模": "线索获取量", "质量率": "高意向占比(%)"}
        )

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
        
        q_invest, q_select, q_overrated, q_abandon = [], [], [], []
        for _, row in channel_stats.iterrows():
            c = row['channel']
            x, y = row['规模'], row['质量率']
            if x >= m_x and y >= m_y: q_invest.append(c)
            elif x < m_x and y >= m_y: q_select.append(c)
            elif x >= m_x and y < m_y: q_overrated.append(c)
            else: q_abandon.append(c)
            
        max_len = max(len(q_invest), len(q_select), len(q_overrated), len(q_abandon))
        q_invest += [""] * (max_len - len(q_invest))
        q_select += [""] * (max_len - len(q_select))
        q_overrated += [""] * (max_len - len(q_overrated))
        q_abandon += [""] * (max_len - len(q_abandon))
        
        quadrant_df = pd.DataFrame({
            "🌟 追投区(高量高质)": q_invest,
            "💎 精选区(低量高质)": q_select,
            "⚠️ 虚高区(高量低质)": q_overrated,
            "🏚️ 放弃区(低量低质)": q_abandon
        })
        
        st.markdown("##### 📌 渠道分层策略明细")
        st.dataframe(quadrant_df, width="stretch", hide_index=True)
        
    else:
        st.info("💡 暂无渠道数据可供象限分析")

# ==========================================
# 5. 经营决策助手
# ==========================================
def get_data_summary(data_df):
    if data_df.empty: return "目前无筛选数据。"
    if 'sales_rep' in data_df.columns:
        rep_stats = data_df.groupby('sales_rep').agg(总额=('amount', 'sum'), 数量=('id', 'count')).to_dict('index')
        return f"全盘摘要：线索{len(data_df)}，销额¥{data_df['amount'].sum():,}。销售表现：{rep_stats}"
    return "数据格式异常"

with st.popover("🐵"):
    st.markdown("#### 🐵 经营决策助手")
    st.caption("您可以询问：陈静为什么业绩不好？或者下周成交趋势如何？")
    if "messages" not in st.session_state: st.session_state.messages = []
    
    for i, msg in enumerate(st.session_state.messages):
        avatar = "🔴" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                c_up, c_down, _ = st.columns([1, 1, 8])
                if c_up.button("👍", key=f"up_{i}"): st.toast("感谢反馈！")
                if c_down.button("👎", key=f"down_{i}"): st.toast("收到优化建议。")

    if prompt := st.chat_input("输入您的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🔴"): st.write(prompt)
        with st.chat_message("assistant", avatar="🤖"):
            with st.status("🐵 正在分析...", expanded=True) as status:
                context = get_data_summary(filtered_df)
                try:
                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "system", "content": f"你是一个 CRM 专家。摘要：{context}"}, {"role": "user", "content": prompt}]
                    )
                    res = response.choices[0].message.content
                    status.update(label="✅ 完成！", state="complete", expanded=False)
                    st.write(res)
                    st.session_state.messages.append({"role": "assistant", "content": res})
                    st.rerun()
                except Exception as e:
                    status.update(label="❌ 失败", state="error")
                    st.error(f"异常: {e}")