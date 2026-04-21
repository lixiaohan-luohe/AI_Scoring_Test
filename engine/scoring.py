# engine/scoring.py
import json
import os
from datetime import timedelta

class LeadEngine:
    @staticmethod
    def load_config():
        """读取配置文件，并确保返回完整的数据结构以防报错"""
        config_path = 'config.json'
        
        # 1. 默认兜底配置：结构必须与你的 config.json 保持 100% 一致
        default_config = {
            "scoring_logic": {
                "base_score": 20, 
                "click_weight": 10, 
                "night_weight": 30, 
                "dm_multiplier": 1.5
            },
            "business_thresholds": {
                "high_score_line": 200, 
                "response_timeout_h": 2, 
                "dormant_days": 7
            },
            "prediction_constants": {
                "avg_cycle_days": 15,
                "high_intensity_factor": 1.5,
                "medium_intensity_factor": 1.2
            }
        }

        # 2. 尝试读取文件
        if os.path.exists(config_path) and os.path.getsize(config_path) > 0:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # 关键：将用户配置合并到默认配置中，防止缺失 Key 导致崩溃
                    for key in default_config:
                        if key in user_config:
                            default_config[key].update(user_config[key])
                    return default_config
            except (json.JSONDecodeError, Exception):
                return default_config
        return default_config

    @staticmethod
    def calculate_score(row):
        """
        核心意向分计算算法
        公式：$$Score = (Base + View \times W_{click} + Night \times W_{night}) \times Multiplier_{DM}$$
        """
        config = LeadEngine.load_config()
        cfg = config['scoring_logic']
        
        s = (cfg['base_score'] + 
             row['view_count'] * cfg['click_weight'] + 
             row['night_visit'] * cfg['night_weight'])
        
        if row.get('is_dm', False): 
            s *= cfg['dm_multiplier']
        return round(s, 1)

    @staticmethod
    def predict_close_date(row):
        """
        预测成交日期 (修复之前 AttributeError 的核心函数)
        逻辑：分值越高，成交动力系数 factor 越大，剩余成交天数越短
        """
        config = LeadEngine.load_config()
        constants = config['prediction_constants']
        
        score = row.get('score', 0)
        
        # 根据意向分确定加速系数
        if score > 250:
            factor = constants.get('high_intensity_factor', 1.5)
        elif score > 150:
            factor = constants.get('medium_intensity_factor', 1.2)
        else:
            factor = 1.0
            
        # 计算预测天数并返回日期对象
        pred_days = constants['avg_cycle_days'] / factor
        return row['create_time'] + timedelta(days=pred_days)