# 大周IM（Dazhou IM）

一个基于 Django 的轻量即时通讯 Web 应用，由 **南昌大周网络科技工作室** 运营。支持公开聊天室、私聊、群聊、入群审核、消息转发/收藏/撤回、文件与图片发送、小游戏等功能，移动端优先。

线上体验：https://cyxadmin.pythonanywhere.com/

## 功能特性

- **公开聊天室**：所有人可发言，支持图片/附件/文件（docx/xlsx 在线预览）、撤回、转发、收藏、@提醒
- **私聊**：一对一消息、已读回执、撤回
- **群聊**：
  - 创建群、群公告、群成员管理（设管理员/移除/禁言/转让群主/解散群）
  - **需审核的群（新增）**：群主可将群设置为「需审核」入群方式，并可选设置入群 PIN 码
    - 输入正确 PIN 码 → 直接入群，无需审批
    - 无 PIN 码 → 提交入群申请，由群主在群资料页审批（同意 / 拒绝）
    - 「发现群聊」页面支持搜索并按入群方式自助加入
- **小游戏**：猜数字、井字棋等（`chat/game_views.py`）
- **账号体系**：注册/登录、邮箱验证（可选）、个人资料与头像、IP 黑名单封禁

## 技术栈

- Python 3.10+ / Django 5.2
- SQLite（可切换 PostgreSQL / MySQL）
- 原生 JavaScript（无前端框架）、Bootstrap 风格模板

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 配置敏感信息（二选一）
#    方式 A：环境变量
export DJANGO_SECRET_KEY='你的随机密钥'
export CHAT_EMAIL_USER='你的发信邮箱'
export CHAT_EMAIL_PASSWORD='你的SMTP授权码'
#    方式 B：本地配置文件（不会被提交到仓库）
cp config/local_secrets.example.py config/local_secrets.py  # 然后填写真实值

# 3. 初始化数据库并启动
python manage.py migrate
python manage.py runserver
```

访问 http://127.0.0.1:8000/ 即可。

## 敏感信息说明

出于安全考虑，代码中**不内置任何真实密钥/凭据**。配置优先级：环境变量 > `config/local_secrets.py`（已在 `.gitignore` 中排除，不会进入公开仓库）。部署到生产环境时请务必设置 `DJANGO_SECRET_KEY`，否则会话与签名数据将不可用。

## 目录结构

```
chatproject/
├── chat/                  # 主应用
│   ├── models.py          # 用户资料/聊天/群聊/入群申请等模型
│   ├── views.py           # 全部视图与 API
│   ├── urls.py            # 路由
│   ├── forms.py           # 注册/登录/建群表单
│   ├── middleware.py      # IP 黑名单中间件
│   ├── game_views.py      # 小游戏
│   ├── migrations/        # 数据库迁移
│   ├── templates/chat/    # 页面模板
│   └── static/chat/       # 前端静态资源
├── config/                # Django 项目配置（settings/urls/wsgi）
├── panel/                 # 可选的管理后台模块（默认未启用，未加入 INSTALLED_APPS）
└── manage.py
```

## 部署到 PythonAnywhere（参考）

1. 将代码上传到 `/home/<用户名>/chatproject`
2. 创建虚拟环境并 `pip install -r requirements.txt`
3. 在 Web 标签页把源码目录指向 `/home/<用户名>/chatproject`，Python 版本选 3.10+
4. 设置环境变量（或创建 `config/local_secrets.py`）填入 `DJANGO_SECRET_KEY` 等
5. `python manage.py migrate` 后点击 **Reload**

## 开源许可

MIT License，见 [LICENSE](LICENSE)。
