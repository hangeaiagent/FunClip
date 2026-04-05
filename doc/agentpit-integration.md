# FunClip AgentPit 集成文档

## 概述

本文档描述 FunClip 项目与 AgentPit 平台的集成方案，包含两大功能模块：

1. **SSO 自动单点登录** — 用户在主站 `app.agentpit.io` 已登录时，访问 `funclip.agentpit.io` 自动完成静默登录
2. **Token 消耗上报** — 供外部 Agent 应用回传 token 消耗数据到 AgentPit 平台

---

## 一、项目结构

```
FunClip/
├── funclip/
│   ├── auth/                        # AgentPit 认证模块
│   │   ├── __init__.py
│   │   ├── config.py                # OAuth2 配置参数
│   │   ├── oauth.py                 # OAuth2 路由（SSO + 弹窗登录 + 回调）
│   │   ├── sso.py                   # SSO 自动登录 JS 脚本
│   │   ├── models.py                # TokenUsage 数据模型（SQLite）
│   │   └── token_report.py          # Token 上报 API 路由
│   └── launch.py                    # Gradio 入口（已集成 OAuth 路由）
├── skills/
│   ├── agentpit-sso/SKILL.md        # SSO 技能定义文档
│   └── agentpit-tokens/SKILL.md     # Token 上报技能定义文档
├── .agentpit/state.json             # AgentPit 功能状态记录
└── requirements.txt                 # 依赖（新增 httpx, PyJWT, sqlalchemy, uvicorn）
```

---

## 二、OAuth2 SSO 单点登录

### 2.1 配置参数

| 参数 | 值 |
|------|----|
| Client ID | `cmnkgi132002o60t9pk3zpt8r` |
| Client Secret | `cmnkgi132002p60t9ssapujw6` |
| 回调地址 | `https://funclip.agentpit.io/api/auth/agentpit/callback` |
| 授权地址 | `https://app.agentpit.io/oauth/authorize` |
| Token 端点 | `https://app.agentpit.io/oauth/token` |
| 用户信息端点 | `https://app.agentpit.io/api/userinfo` |
| 登录按钮名称 | agentpit 授权登陆 |

所有参数均支持通过环境变量覆盖（见 `funclip/auth/config.py`）。

### 2.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/auth/agentpit/sso?returnUrl=/` | SSO 入口，302 重定向到 AgentPit 授权页 |
| GET | `/api/auth/agentpit/login` | 弹窗登录入口 |
| GET | `/api/auth/agentpit/callback?code=xxx&state=xxx` | OAuth 回调，处理授权码换 token |
| GET | `/auth/sso/callback` | 前端 SSO 回调页，从 URL hash 提取 token |
| GET | `/api/auth/agentpit/logout` | 登出，清除本地存储 |

### 2.3 SSO 完整流程

```
用户从 app.agentpit.io 点击进入 funclip.agentpit.io
  │
  ▼
页面加载 → 检查 localStorage 中的 agentpit_token
  │
  ├── 有 token → 正常使用（已登录）
  │
  └── 无 token → shouldAutoSso() 检查
        │
        ├── 不满足条件（已尝试/回调页/有错误参数）→ 显示未登录页面
        │
        └── 满足条件 → 标记 sessionStorage('sso_attempted')
              │
              ▼
        重定向 → /api/auth/agentpit/sso?returnUrl=/当前路径
              │
              ▼
        302 → AgentPit 授权页（state=sso:/当前路径）
              │
              ├── 已登录且已授权 → 静默回调（无需用户操作）
              ├── 已登录未授权 → 显示授权确认页
              └── 未登录 → 显示登录页
              │
              ▼
        回调 → /api/auth/agentpit/callback?code=xxx&state=sso:/路径
              │
              ▼
        后端：code 换 access_token → 获取用户信息 → 生成 JWT
              │
              ▼
        返回 HTML → JS 跳转到 /auth/sso/callback#token=xxx&user=xxx
              │
              ▼
        前端回调页：解析 hash → 存入 localStorage → 跳转原始页面
```

### 2.4 防无限循环机制

通过 `sessionStorage` 中的 `sso_attempted` 标记控制：

| 场景 | 行为 |
|------|------|
| 首次访问，无 token | 触发一次 SSO 重定向 |
| SSO 成功 | 清除标记，正常使用 |
| SSO 失败 | 跳转 `/?sso_error=xxx`，不再重试 |
| 同一 session 刷新页面 | 标记已存在，不触发 SSO |
| 新标签页/新 session | 重新尝试一次 SSO |
| 访问 `/auth/sso/callback` 或有 `sso_error` 参数 | 不触发 SSO |

### 2.5 安全设计

- **Token 通过 URL hash 传递**：hash 部分不会发送到服务器，不出现在访问日志中
- **敏感信息立即清除**：回调页读取 hash 后通过 `window.history.replaceState` 清除 URL
- **state 参数隔离**：`sso:` 前缀区分 SSO 模式和弹窗模式，互不影响
- **JWT 24 小时过期**：session token 有效期 24 小时

### 2.6 两种登录方式

1. **SSO 自动登录**：页面加载时自动检测并静默完成（推荐）
2. **按钮弹窗登录**：点击页面右上角 "agentpit 授权登陆" 按钮，弹窗完成 OAuth 后通过 `postMessage` 回传 token

---

## 三、Token 消耗上报接口

### 3.1 接口信息

| 项目 | 值 |
|------|----|
| 路径 | `POST /api/v1/tokens/report` |
| 认证 | `Authorization: Bearer <ApiKey>` |
| 数据存储 | SQLite（`token_usage.db`，表名 `apbase_token_usage`） |

### 3.2 请求体字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agentId` | string | 是 | Agent ID |
| `tokensUsed` | int | 是 | 总 token 消耗量（正整数） |
| `inputTokens` | int | 否 | 输入 token 数 |
| `outputTokens` | int | 否 | 输出 token 数 |
| `startedAt` | string | 是 | 开始时间（ISO 8601） |
| `endedAt` | string | 是 | 结束时间（ISO 8601），必须晚于 startedAt |
| `modelName` | string | 否 | AI 模型名称（如 gpt-4, claude-3） |
| `requestId` | string | 否 | 请求追踪 ID |
| `metadata` | object | 否 | 扩展 JSON 数据 |

### 3.3 响应格式

**成功 (200)**：

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "agentId": "agent_id",
    "tokensUsed": 1500,
    "startedAt": "2025-01-01T00:00:00.000Z",
    "endedAt": "2025-01-01T00:00:05.000Z",
    "createdAt": "2025-01-01T00:00:06.000Z"
  }
}
```

**失败 (4xx/5xx)**：

```json
{
  "success": false,
  "error": "错误描述"
}
```

### 3.4 错误码

| 状态码 | 说明 |
|--------|------|
| 401 | 缺少认证信息 / 无效的 API Key |
| 400 | 参数校验失败（tokensUsed 非正整数、时间格式错误、startedAt >= endedAt） |
| 500 | 服务器内部错误 |

### 3.5 调用示例

```bash
curl -X POST https://funclip.agentpit.io/api/v1/tokens/report \
  -H "Authorization: Bearer agp_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "agentId": "agent_id_here",
    "tokensUsed": 1500,
    "inputTokens": 1000,
    "outputTokens": 500,
    "startedAt": "2025-01-01T00:00:00.000Z",
    "endedAt": "2025-01-01T00:00:05.000Z",
    "modelName": "gpt-4",
    "requestId": "req_abc123"
  }'
```

### 3.6 数据模型

`apbase_token_usage` 表结构：

| 字段 | 类型 | 索引 | 说明 |
|------|------|------|------|
| id | VARCHAR (PK) | - | UUID 主键 |
| agent_id | VARCHAR | YES | Agent ID |
| application_id | VARCHAR | YES | 应用 ID |
| user_id | VARCHAR | YES | 用户 ID |
| tokens_used | INTEGER | - | 总消耗量 |
| input_tokens | INTEGER | - | 输入 token（可选） |
| output_tokens | INTEGER | - | 输出 token（可选） |
| started_at | DATETIME | - | 调用开始时间 |
| ended_at | DATETIME | - | 调用结束时间 |
| model_name | VARCHAR | - | 模型名称（可选） |
| request_id | VARCHAR | - | 请求 ID（可选） |
| metadata_json | TEXT | - | 扩展 JSON（可选） |
| created_at | DATETIME | YES | 记录创建时间 |
| updated_at | DATETIME | - | 记录更新时间 |

---

## 四、部署说明

### 4.1 安装依赖

```bash
pip install httpx PyJWT sqlalchemy uvicorn
```

或直接：

```bash
pip install -r requirements.txt
```

### 4.2 环境变量（可选覆盖）

```bash
export AGENTPIT_CLIENT_ID="cmnkgi132002o60t9pk3zpt8r"
export AGENTPIT_CLIENT_SECRET="cmnkgi132002p60t9ssapujw6"
export AGENTPIT_REDIRECT_URI="https://funclip.agentpit.io/api/auth/agentpit/callback"
export SESSION_SECRET="your-production-secret"
export TOKEN_DB_PATH="/path/to/token_usage.db"
```

### 4.3 启动服务

```bash
cd funclip
python launch.py --listen --port 7860
```

服务启动后：
- Gradio UI：`http://0.0.0.0:7860/`
- OAuth SSO：`/api/auth/agentpit/sso`
- Token 上报：`POST /api/v1/tokens/report`

### 4.4 技术栈

| 组件 | 技术 |
|------|------|
| UI 框架 | Gradio（基于 FastAPI） |
| OAuth HTTP 客户端 | httpx |
| JWT 签发 | PyJWT (HS256) |
| 数据库 | SQLite + SQLAlchemy |
| ASGI 服务器 | uvicorn |

---

## 五、Skills 技能文件

项目包含两个 AgentPit 技能定义文件，供 Cursor AI 等工具调用：

- **`skills/agentpit-sso/SKILL.md`** — 指导生成 SSO 自动单点登录代码
- **`skills/agentpit-tokens/SKILL.md`** — 指导生成 Token 消耗上报接口代码

技能文件遵循 AgentPit Skills 规范（参考 [hangeaiagent/agentpit-Skills](https://github.com/hangeaiagent/agentpit-Skills)），包含前置检查、用户输入收集、代码生成规范和输出模板。
