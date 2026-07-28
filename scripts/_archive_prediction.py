#!/usr/bin/env python3
"""预测归档——把 Workflow 终裁结果写入 data/predictions/<type>_predictions.csv"""
import csv, os, sys, json
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED_DIR = os.path.join(BASE, 'data', 'predictions')
MANIFEST_PATH = os.path.join(BASE, 'data', 'processed', 'manifest.json')

SCHEMAS = {
    'ssq': ['period_id','pred_time','compound_red','compound_blue',
            's1_red','s1_blue','s2_red','s2_blue','s3_red','s3_blue','dan_ma','notes'],
    'dlt': ['period_id','pred_time','compound_front','compound_back',
            's1_front','s1_back','s2_front','s2_back','s3_front','s3_back','dan_ma','notes'],
    'kl8': ['period_id','pred_time','compound',
            's1','s2','s3','dan_ma','notes'],
    'pl5': ['period_id','pred_time','s1','s2','s3','notes'],
    'qxc': ['period_id','pred_time','compound_front','compound_back',
            's1_front','s1_back','s2_front','s2_back','s3_front','s3_back','notes'],
}

def append_prediction(lottery_type: str, data: dict):
    """追加一行预测记录"""
    if lottery_type not in SCHEMAS:
        raise ValueError(f'未知彩种: {lottery_type}，可选: {list(SCHEMAS.keys())}')

    csv_path = os.path.join(PRED_DIR, f'{lottery_type}_predictions.csv')
    columns = SCHEMAS[lottery_type]

    # 确保目录存在
    os.makedirs(PRED_DIR, exist_ok=True)

    # 确保文件存在且有表头
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)

    # 填充默认值
    data.setdefault('pred_time', datetime.now(CST).strftime('%Y-%m-%dT%H:%M:%S+08:00'))
    for col in columns:
        data.setdefault(col, '')

    # 去重：同期号已存在则跳过
    existing = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing.append(row)

    if any(r['period_id'] == str(data['period_id']) for r in existing):
        print(f'⏭️  {lottery_type} 期号 {data["period_id"]} 已存在，跳过')
        return

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in existing:
            writer.writerow(row)
        writer.writerow({k: data.get(k, '') for k in columns})

    # 更新 manifest
    try:
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        manifest = {}

    manifest.setdefault('predictions', {})
    manifest['predictions'][lottery_type] = {
        'last_period': str(data['period_id']),
        'last_pred_time': data['pred_time'],
        'total': len(existing) + 1,
        'csv': f'data/predictions/{lottery_type}_predictions.csv',
    }

    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f'✅ {lottery_type} 期号 {data["period_id"]} 已归档 → data/predictions/{lottery_type}_predictions.csv')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('用法: python _archive_prediction.py <彩种> <JSON数据>')
        print('示例: python _archive_prediction.py ssq \'{"period_id":"2026087",...}\'')
        sys.exit(1)

    lottery = sys.argv[1]
    try:
        payload = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        print(f'❌ JSON解析失败: {e}')
        sys.exit(1)

    append_prediction(lottery, payload)
