import os

from application.settings import BASE_DIR

# ================================================= #
# *************** mysql数据库 配置  *************** #
# ================================================= #
# 数据库 ENGINE ，默认演示使用 sqlite3 数据库，正式环境建议使用 mysql 数据库
# sqlite3 设置
# DATABASE_ENGINE = "django.db.backends.sqlite3"
# DATABASE_NAME = os.path.join(BASE_DIR, "db.sqlite3")

# 使用mysql时，改为此配置
DATABASE_ENGINE = "django.db.backends.mysql"
DATABASE_NAME = 'django-vue3-admin' # mysql 时使用

# 数据库地址 改为自己数据库地址
DATABASE_HOST = '127.0.0.1'
# # 数据库端口
DATABASE_PORT = 3306
# # 数据库用户名
DATABASE_USER = "root"
# # 数据库密码
DATABASE_PASSWORD = 'DVADMIN3'

# 表前缀
TABLE_PREFIX = "dvadmin_"
# ================================================= #
# ******** redis配置，无redis 可不进行配置  ******** #
# ================================================= #
REDIS_DB = 1
CELERY_BROKER_DB = 3
REDIS_PASSWORD = 'DVADMIN3'
REDIS_HOST = '127.0.0.1'
REDIS_URL = f'redis://:{REDIS_PASSWORD or ""}@{REDIS_HOST}:6379'
# ================================================= #
# ****************** 功能 启停  ******************* #
# ================================================= #
DEBUG = True
# 启动登录详细概略获取(通过调用api获取ip详细地址。如果是内网，关闭即可)
ENABLE_LOGIN_ANALYSIS_LOG = True
# 登录接口 /api/token/ 是否需要验证码认证，用于测试，正式环境建议取消
LOGIN_NO_CAPTCHA_AUTH = True
# ================================================= #
# ****************** 其他 配置  ******************* #
# ================================================= #

ALLOWED_HOSTS = ["*"]
# 列权限中排除App应用
COLUMN_EXCLUDE_APPS = []

# ================================================= #
# *************** 品牌 / 应用名称 ***************** #
# ================================================= #
# 应用名称: 用于「注册验证 / 找回密码」等系统邮件文案; 前端 logo/名称见 web/.env
APP_NAME = 'Hongkong HK'

# ================================================= #
# *************** AI Key 池加密 ****************** #
# ================================================= #
# 用于加密数据库中渠道/平台的 AI API Key（Fernet key）。
# 生成: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 未配置时会回退用 SECRET_KEY 派生（仅开发可用；生产务必显式配置且不要更换）。
AI_KEY_ENCRYPTION_KEY = ''
# Key 轮换策略: lru（默认，最久未用优先） / random / highest_credit
AI_KEY_STRATEGY = 'lru'
# 余额自动刷新间隔（秒），列表/额度接口按需刷新
AI_KEY_BALANCE_TTL = 900
# 渠道未配置非 QVeris Key（DeepSeek/视觉/RAG）时是否回退平台 Key。
# True=平滑过渡（默认）；False=直接拒绝，额度隔离最彻底。可在超管前端切换（DB 优先）。
AI_KEY_FALLBACK_TO_GLOBAL = True
