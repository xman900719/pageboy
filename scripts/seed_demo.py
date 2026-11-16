#!/usr/bin/env python3
"""Seed synthetic (never actual exam) practice items via reviewed-source API."""
import os, json, urllib.request
from test_data_policy import require_owner_test_data_approval
require_owner_test_data_approval('seed_demo.py（开发环境虚构演示题目）')
BASE=os.getenv('SHUTONG_API_URL','http://127.0.0.1:8000')
TOKEN=os.environ.get('SHUTONG_TOKEN')
if not TOKEN: raise SystemExit('Set SHUTONG_TOKEN to the same secret used by your local API')

# 防呆：目标服务自报 env=prod 时拒绝写入虚构演示数据（旧版无 env 字段则视为非生产）。
with urllib.request.urlopen(BASE+'/health/live',timeout=10) as response:
    if json.load(response).get('env')=='prod': raise SystemExit('目标为生产环境(env=prod)，拒绝写入虚构演示数据')

def send(path,payload=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode('utf-8') if payload is not None else None,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},method='POST' if payload is not None else 'GET')
    with urllib.request.urlopen(req,timeout=10) as response:
        return json.load(response)

for subject, name in [('math','数学'),('physics','物理'),('chinese','语文'),('english','英语')]:
    src=send('/api/admin/sources',{'title':f'{name}虚构演示题源（不是历年中考真题）','subject':subject,'rights_status':'personal_use_reviewed','verified':True})['id']
    for i in range(5):
        q=send('/api/admin/questions',{'source_document_id':src,'stem':f'{name}合成演示题 {i+1}：选出 B 选项（仅供系统测试）','kind':'single_choice','options':['A. 错误示意','B. 正确示意'],'correct_answer':'B','knowledge_ids':[f'{subject}.demo.basic'],'max_points':1})['id']
        send(f'/api/admin/questions/{q}/review',{})
        send(f'/api/admin/questions/{q}/publish',{})
print('seed complete: synthetic items only; do not use as real exam training data')
