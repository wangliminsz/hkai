#!/bin/bash
# 激活 Python 环境
source /home/hkai/app/venv/bin/activate
# 运行 Python 脚本
python3 /home/hkai/app/backend/manage.py funds_analysis >> /home/hkai/app/tmp/funds_2.log 2>&1
