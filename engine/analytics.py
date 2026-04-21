# engine/analytics.py
import pandas as pd

class DiagnosticEngine:
    @staticmethod
    def get_data_summary(data_df):
        """把原始的 DataFrame 翻译成 AI 能听懂的数据总结"""
        if data_df.empty:
            return "目前无筛选数据。"
        
        # 提取关键销售统计
        rep_stats = data_df.groupby('sales_rep').agg(
            成交总额=('amount', 'sum'),
            线索总数=('id', 'count'),
            平均响应时间=('response_time_h', 'mean')
        ).to_dict('index')
        
        summary = (
            f"全盘摘要：总线索 {len(data_df)}，总销额 ¥{data_df['amount'].sum():,}。"
            f"S级线索数：{len(data_df[data_df['score'] > 200])}。\n"
            f"销售明细看板：{rep_stats}"
        )
        return summary

    @staticmethod
    def get_system_prompt(context):
        """定义 AI 诊断师的专家人设"""
        return {
            "role": "system",
            "content": (
                "你是一个资深的 CRM 数字化经营专家。以下是实时业务数据：\n"
                f"{context}\n\n"
                "请根据以上数据提供诊断。你的风格必须：\n"
                "1. 结论优先：先说哪个环节出了大问题。\n"
                "2. 深度分析：不要只读数字，要结合 CRM 逻辑分析原因（如响应时间过长）。\n"
                "3. 动作导向：给老板提 3 条具体的管理建议。"
            )
        }