import json

# 定义绝对标准的配置内容
clean_config = {
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

# 强行写入文件，确保没有隐藏字符
with open('config.json', 'w', encoding='utf-8') as f:
    json.dump(clean_config, f, indent=4, ensure_ascii=False)

print("✅ config.json 已成功重置，现在它是绝对干净的了！")