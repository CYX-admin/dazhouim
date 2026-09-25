# -*- coding: utf-8 -*-
# 生产环境敏感配置示例 —— 复制为 config/local_secrets.py 后填写真实值
# 注意：config/local_secrets.py 已被 .gitignore 排除，不会提交到仓库
SECRETS = {
    # Django 会话签名密钥（生产环境必填，可用 `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` 生成）
    'DJANGO_SECRET_KEY': '请替换为随机密钥',
    # 邮箱 SMTP 配置（可选，用于修改邮箱时的验证邮件）
    'CHAT_EMAIL_HOST': 'smtp.qq.com',
    'CHAT_EMAIL_PORT': '465',
    'CHAT_EMAIL_USER': '你的发信邮箱',
    'CHAT_EMAIL_PASSWORD': '你的SMTP授权码',
}
