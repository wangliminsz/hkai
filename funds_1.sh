#!/bin/bash
# 激活 Python 环境
source /home/hkai/app/venv/bin/activate
# 运行 Python 脚本
python3 /home/hkai/app/backend/manage.py funds_daily >> /home/hkai/app/tmp/funds_1.log 2>&1
