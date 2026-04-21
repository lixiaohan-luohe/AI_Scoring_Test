import streamlit as st
import pandas as pd

def load_data():
    try:
        conn = st.connection("mysql", type="sql")
        
        # ✨ 核心逻辑：SQL 多表关联
        # 我们同时关联归属人(u1)和创建人(u2)的姓名
        query = """
        SELECT 
            c.*, 
            u1.name AS owner_name, 
            u2.name AS creator_name
        FROM contacts c
        LEFT JOIN users u1 ON c.owner_id = u1.userid
        LEFT JOIN users u2 ON c.create_user_id = u2.userid
        """
        df = conn.query(query, ttl=60)
        
        if df is not None and not df.empty:
            # 1. ✨ 字段重新映射 ✨
            # 现在我们直接用关联出来的姓名作为展示字段
            df['customer'] = df['corp_name'].fillna(df['user_name']).fillna("未知客户")
            
            mapping = {
                'contact_id': 'id',
                'interactive_score': 'view_count',
                'from_channel_name': 'channel',
                'customer_stage': 'stage',
                'owner_name': 'sales_rep', # 👈 这里变回了真实的姓名
                'creator_name': 'creator'  # 👈 这里变回了真实的姓名
            }
            df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})

            # 2. 状态与时间清洗
            stage_map = {1: '初访', 2: '方案', 3: '报价', 4: '成交', '1': '初访'}
            if 'stage' in df.columns:
                df['stage'] = df['stage'].replace(stage_map).fillna('初访')

            for col in ['create_time', 'last_follow_time']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], unit='ms', errors='coerce')

            # 3. 补全数值与兜底字段
            df['view_count'] = df['view_count'].fillna(0).astype(int)
            df['score'] = df['view_count']
            df['pred_date'] = df['create_time'] + pd.Timedelta(days=15)
            
            # 补齐 creator 和 sales_rep 的空值
            df['sales_rep'] = df['sales_rep'].fillna("未分配")
            df['creator'] = df['creator'].fillna("系统导入")
            
            required = {'night_visit': 0, 'is_dm': False, 'is_contacted': False, 'amount': 0}
            for col, val in required.items():
                if col not in df.columns:
                    df[col] = val
            
            return df
    except Exception as e:
        st.sidebar.error(f"❌ 数据库关联失败: {e}")
    return pd.DataFrame()