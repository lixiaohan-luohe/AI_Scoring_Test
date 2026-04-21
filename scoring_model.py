import random
from datetime import datetime, timedelta

# ==========================================
# 1. 原子能力层 (The Hands - Atomic Tools)
# ==========================================

class LeadAtomicTools:
    """
    这些函数就是“协议化”的工具，每一个只负责一个独立的业务逻辑。
    """
    
    @staticmethod
    def calculate_score(lead):
        """意向评分协议：计算线索的实时意向分"""
        base_score = 20
        click_score = lead['view_count'] * 10
        night_score = lead['night_visit'] * 30
        multiplier = 1.5 if lead['is_decision_maker'] else 1.0
        
        total_score = (base_score + click_score + night_score) * multiplier
        return round(total_score, 2)

    @staticmethod
    def check_response_alert(lead, current_time):
        """时效预警协议：判定是否为‘高分未联系’"""
        # 逻辑：得分 > 200 且 超过 2 小时未联系
        time_diff = (current_time - lead['distribute_time']).total_seconds() / 3600
        if lead['score'] > 200 and not lead['is_contacted'] and time_diff > 2:
            return True, round(time_diff, 1)
        return False, 0

    @staticmethod
    def check_dormancy(lead, current_time):
        """沉默唤醒协议：判定优质线索是否已冷淡"""
        # 逻辑：历史最高分是 A 级以上，且超过 7 天没有活跃
        days_inactive = (current_time - lead['last_active_time']).days
        if lead['score'] > 150 and days_inactive >= 7:
            return True, days_inactive
        return False, 0

# ==========================================
# 2. 数据模拟层 (Mock Data Generation)
# ==========================================

def generate_mock_leads(count=50):
    channels = ['百度广告', '抖音投放', '官网搜索', '朋友推荐', '转介绍']
    leads = []
    now = datetime.now()
    
    for i in range(count):
        # 随机生成一些属性
        lead = {
            'id': f"L{1000 + i}",
            'view_count': random.randint(0, 20),
            'night_visit': random.randint(0, 5),
            'is_decision_maker': random.choice([True, False]),
            'is_contacted': random.choice([True, False]),
            'channel': random.choice(channels),
            'amount': random.choice([0, 0, 0, 5000, 12000, 50000]), # 模拟成交金额
            # 模拟时间：过去 30 天内
            'distribute_time': now - timedelta(hours=random.randint(1, 720)),
            'last_active_time': now - timedelta(days=random.randint(0, 15)),
        }
        # 调用原子工具计算分数
        lead['score'] = LeadAtomicTools.calculate_score(lead)
        leads.append(lead)
    return leads

# ==========================================
# 3. 业务看板展现层 (Visual Dashboard)
# ==========================================

def run_bi_dashboard(period_days=7):
    leads = generate_mock_leads(50)
    now = datetime.now()
    start_date = now - timedelta(days=period_days)
    
    # 过滤时间段数据
    period_leads = [l for l in leads if l['distribute_time'] > start_date]
    total_sales = sum(l['amount'] for l in period_leads)
    
    print(f"\n{'='*60}")
    print(f"📊 CRM 智能线索分析看板 (当前维度: 过去 {period_days} 天)")
    print(f"{'='*60}")

    # --- [经营核心区] ---
    print(f"\n【经营核心区】")
    print(f"💰 总销售额: ¥{total_sales:,}")
    print(f"📈 新增线索: {len(period_leads)} 条")
    print(f"🎯 S/A级优质占比: {len([l for l in period_leads if l['score'] > 150]) / len(period_leads) * 100:.1f}%")

    # --- [预测层] ---
    print(f"\n【预测层 - 🚩 高分未联系预警】")
    print(f"{'ID':<8} | {'意向分':<6} | {'超时时长':<8} | {'负责销售'}")
    print("-" * 45)
    for l in period_leads:
        is_alert, hours = LeadAtomicTools.check_response_alert(l, now)
        if is_alert:
            print(f"{l['id']:<8} | {l['score']:<9} | {hours:<10}h | 销售员_{random.randint(1,5)}")

    print(f"\n【预测层 - 💤 优质沉默唤醒清单】")
    print(f"{'ID':<8} | {'历史分':<6} | {'沉默天数':<8} | {'所属渠道'}")
    print("-" * 45)
    for l in leads: # 全量查沉默
        is_dormant, days = LeadAtomicTools.check_dormancy(l, now)
        if is_dormant:
            print(f"{l['id']:<8} | {l['score']:<9} | {days:<10}天 | {l['channel']}")

    # --- [效率诊断区] ---
    print(f"\n【效率诊断 - 渠道质量 ROI 对比】")
    print(f"{'渠道名称':<10} | {'线索量':<6} | {'S级占比':<8} | {'总贡献额'}")
    print("-" * 45)
    channels = set(l['channel'] for l in leads)
    for c in channels:
        c_leads = [l for l in leads if l['channel'] == c]
        s_leads = [l for l in c_leads if l['score'] > 200]
        c_sales = sum(l['amount'] for l in c_leads)
        s_rate = (len(s_leads)/len(c_leads)*100) if c_leads else 0
        print(f"{c:<10} | {len(c_leads):<9} | {s_rate:<9.1f}% | ¥{c_sales:,}")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    # 模拟老板点击“过去 7 天”
    run_bi_dashboard(7)