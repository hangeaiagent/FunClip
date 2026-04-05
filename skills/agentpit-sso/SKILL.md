---
name: agentpit-sso
description: 为 AgentPit 子应用生成 SSO 自动单点登录功能，包含后端 OAuth 端点、前端回调页和防循环机制
user-invocable: true
---

# AgentPit SSO 自动单点登录生成

帮助开发者为 AgentPit 子域名应用（如 `funclip.agentpit.io`）生成 SSO 自动单点登录功能。用户在主站 `app.agentpit.io` 已登录的情况下，访问子应用时自动完成静默登录，无需手动点击授权按钮。

**工具使用：** 收集用户输入时使用 `AskUserQuestion` 工具。

---

## 前置条件检查

### 1. 环境检查

确认当前目录是目标子应用项目根目录：

```
📂 当前工作目录: /path/to/FunClip

检查以下文件/目录是否存在：
✅ funclip/launch.py（Gradio 入口）
✅ funclip/auth/（认证模块目录）
✅ funclip/auth/config.py（OAuth 配置）
✅ requirements.txt
```

如有缺失，提示用户确认项目结构。

### 2. 检查现有 OAuth 集成

- 确认项目是否已有 AgentPit OAuth 登录
- 如已有 → SSO 模式将在其基础上新增，共享同一个回调地址
- 如未有 → 需先完成基础 OAuth 集成

---

## 用户输入收集

### 第一步：确认应用信息

使用 `AskUserQuestion` 收集：

```
📋 SSO 配置信息

1. 子应用域名（如 funclip.agentpit.io）：
2. 主站 OAuth 授权地址（默认: https://app.agentpit.io/oauth/authorize）：
3. OAuth 回调路径（默认: /api/auth/agentpit/callback）：
4. 前端 SSO 回调页路径（默认: /auth/sso/callback）：
5. 项目技术栈：
   a. Python Gradio + FastAPI（默认）
   b. 其他（请描述）
6. OAuth Client ID：
7. OAuth Client Secret：
8. 登录按钮名称（默认: agentpit 授权登陆）：
```

### 第二步：确认功能范围

使用 `AskUserQuestion` 询问：

> 请确认 SSO 功能范围：
>
> 1. 仅新增 SSO 静默重定向模式（保留现有弹窗登录）✅ 推荐
> 2. 替换弹窗模式，仅使用 SSO 重定向
> 3. 自定义（请描述）

---

## SSO 完整流程

```
用户从 app.agentpit.io 点击进入子应用（funclip.agentpit.io）
  |
  v
前端页面初始化，检查本地 session/token
  |
  ├── 有 token → 正常验证登录（原有逻辑）
  |
  └── 无 token → should_auto_sso() 检查
        |
        ├── 不满足条件 → 正常显示页面（未登录状态）
        |
        └── 满足条件 → mark_sso_attempted()
              |
              v
        重定向到 /api/auth/agentpit/sso?returnUrl=/当前路径
              |
              v
        后端 302 重定向到 AgentPit 授权页（state=sso:/当前路径）
              |
              ├── 用户已登录且已授权 → AgentPit 自动回调（无需用户操作）
              |
              ├── 用户已登录未授权 → 显示授权确认页
              |
              └── 用户未登录 → 显示登录页
              |
              v
        回调 /api/auth/agentpit/callback?code=xxx&state=sso:/路径
              |
              v
        后端处理 code，生成 session
              |
              v
        返回 HTML 页面，JS 跳转到 /auth/sso/callback#token=xxx&user=xxx
              |
              v
        SsoCallbackPage 解析 hash，保存 session
              |
              v
        登录成功，跳转到原始页面
```

---

## 代码生成规范

**⚠️ 以下规范必须严格遵守，不得违反：**

### 1. 后端：OAuth 配置文件

**文件：** `funclip/auth/config.py`

```python
import os

AGENTPIT_CLIENT_ID = os.getenv("AGENTPIT_CLIENT_ID", "your_client_id")
AGENTPIT_CLIENT_SECRET = os.getenv("AGENTPIT_CLIENT_SECRET", "your_client_secret")
AGENTPIT_AUTHORIZE_URL = os.getenv("AGENTPIT_AUTHORIZE_URL", "https://app.agentpit.io/oauth/authorize")
AGENTPIT_TOKEN_URL = os.getenv("AGENTPIT_TOKEN_URL", "https://app.agentpit.io/oauth/token")
AGENTPIT_USERINFO_URL = os.getenv("AGENTPIT_USERINFO_URL", "https://app.agentpit.io/api/userinfo")
AGENTPIT_REDIRECT_URI = os.getenv("AGENTPIT_REDIRECT_URI", "https://funclip.agentpit.io/api/auth/agentpit/callback")
AGENTPIT_LOGIN_BUTTON_NAME = os.getenv("AGENTPIT_LOGIN_BUTTON_NAME", "agentpit 授权登陆")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-production")
```

### 2. 后端：SSO 入口端点

**端点：** `GET /api/auth/agentpit/sso?returnUrl=/`

**逻辑：**
- 将 `returnUrl` 编码到 OAuth `state` 参数中（格式：`sso:/path`）
- 302 重定向到 AgentPit 授权页

```python
# funclip/auth/oauth.py
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from urllib.parse import urlencode, quote
import httpx, jwt, json, time
from .config import *

router = APIRouter()

@router.get("/api/auth/agentpit/sso")
async def sso_redirect(returnUrl: str = "/"):
    state = f"sso:{returnUrl}"
    params = {
        "client_id": AGENTPIT_CLIENT_ID,
        "redirect_uri": AGENTPIT_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    authorize_url = f"{AGENTPIT_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url=authorize_url)
```

### 3. 后端：OAuth 回调端点

**端点：** `GET /api/auth/agentpit/callback`

通过 `state` 参数前缀 `sso:` 区分模式：

- **SSO 模式**（`state` 以 `sso:` 开头）：返回 HTML 页面，通过 JS 跳转到前端 SSO 回调页
- **弹窗模式**（其他情况）：保持原有 `postMessage` 行为不变

**安全要求：** Token 通过 URL hash（`#`）传递而非 query params，避免 token 出现在服务器日志中。

```python
@router.get("/api/auth/agentpit/callback")
async def oauth_callback(code: str, state: str = ""):
    # 用 code 换取 access_token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(AGENTPIT_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": AGENTPIT_REDIRECT_URI,
            "client_id": AGENTPIT_CLIENT_ID,
            "client_secret": AGENTPIT_CLIENT_SECRET,
        })
        token_data = token_resp.json()
    
    access_token = token_data.get("access_token")
    
    # 获取用户信息
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(AGENTPIT_USERINFO_URL, headers={
            "Authorization": f"Bearer {access_token}"
        })
        user_info = user_resp.json()
    
    # 生成 JWT session token
    session_token = jwt.encode({
        "sub": user_info.get("id"),
        "name": user_info.get("name"),
        "email": user_info.get("email"),
        "exp": int(time.time()) + 86400,
    }, SESSION_SECRET, algorithm="HS256")
    
    encoded_user = quote(json.dumps(user_info))
    
    if state.startswith("sso:"):
        return_url = state[4:]
        html = f"""<!DOCTYPE html><html><body><script>
        window.location.replace(
            '/auth/sso/callback?returnUrl={return_url}#token={session_token}&user={encoded_user}'
        );
        </script></body></html>"""
        return HTMLResponse(content=html)
    else:
        # 弹窗模式：postMessage
        html = f"""<!DOCTYPE html><html><body><script>
        window.opener.postMessage({{
            type: 'agentpit-oauth',
            token: '{session_token}',
            user: '{encoded_user}'
        }}, '*');
        window.close();
        </script></body></html>"""
        return HTMLResponse(content=html)
```

### 4. 前端：SSO 回调页（Gradio 内嵌 HTML）

**端点：** `GET /auth/sso/callback`

```python
@router.get("/auth/sso/callback")
async def sso_callback_page():
    html = """<!DOCTYPE html>
<html><head><title>登录中...</title></head>
<body>
<div style="text-align:center;margin-top:20vh;font-size:18px;">登录中...</div>
<script>
(function() {
    var hash = window.location.hash.substring(1);
    var params = new URLSearchParams(hash);
    var token = params.get('token');
    var userStr = params.get('user');
    var returnUrl = new URLSearchParams(window.location.search).get('returnUrl') || '/';
    
    // 立即清除 URL 中的敏感信息
    window.history.replaceState(null, '', window.location.pathname);
    
    if (token && userStr) {
        try {
            localStorage.setItem('agentpit_token', token);
            localStorage.setItem('agentpit_user', decodeURIComponent(userStr));
            sessionStorage.removeItem('sso_attempted');
            window.location.replace(returnUrl);
        } catch(e) {
            window.location.replace('/?sso_error=parse_failed');
        }
    } else {
        window.location.replace('/?sso_error=missing_token');
    }
})();
</script>
</body></html>"""
    return HTMLResponse(content=html)
```

### 5. 前端：SSO 辅助脚本（注入 Gradio 页面）

**文件：** `funclip/auth/sso.py`

```python
SSO_AUTO_LOGIN_JS = """
<script>
(function() {
    var SSO_KEY = 'sso_attempted';
    
    function shouldAutoSso() {
        if (window.location.pathname.startsWith('/auth/sso/callback')) return false;
        if (new URLSearchParams(window.location.search).has('sso_error')) return false;
        if (sessionStorage.getItem(SSO_KEY)) return false;
        if (localStorage.getItem('agentpit_token')) return false;
        return true;
    }
    
    if (shouldAutoSso()) {
        sessionStorage.setItem(SSO_KEY, 'true');
        var returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = '/api/auth/agentpit/sso?returnUrl=' + returnUrl;
    }
})();
</script>
"""
```

### 6. Gradio 集成

在 `launch.py` 中集成 OAuth 路由和 SSO 自动登录：

```python
# launch.py 中添加
from auth.oauth import router as oauth_router
from auth.sso import SSO_AUTO_LOGIN_JS

# Gradio Blocks 内添加 SSO JS
with gr.Blocks(theme=theme, head=SSO_AUTO_LOGIN_JS) as funclip_service:
    # ... 现有 UI 代码 ...
    pass

# 挂载 FastAPI 路由
app = gr.mount_gradio_app(app, funclip_service, path="/")
app.include_router(oauth_router)
```

---

## 防无限循环机制

使用 `sessionStorage` 中的 `sso_attempted` 标记防止无限重定向：

| 场景 | 行为 |
|------|------|
| 首次访问，无 token | 触发一次 SSO 重定向 |
| SSO 成功 | 清除标记，正常使用 |
| SSO 失败（用户未在主站登录） | 跳转到 `/?sso_error=xxx`，不再重试 |
| 用户刷新页面（同一 session） | 标记已存在，不触发 SSO |
| 用户新开浏览器标签 | 新 session，会再次尝试 SSO |
| 访问 `/auth/sso/callback` | 不触发 SSO |

---

## 安全注意事项

1. **Token 传递安全**：Token 通过 URL hash（`#`）传递，不会发送到服务器，不会出现在 Nginx/Caddy 访问日志中
2. **敏感信息清除**：SSO 回调页读取 hash 后立即通过 `window.history.replaceState` 清除 URL 中的敏感信息
3. **防循环攻击**：每个 session 最多触发一次自动 SSO，避免被用于循环攻击
4. **state 参数隔离**：`state` 参数通过前缀 `sso:` 区分模式，不影响原有弹窗回调

---

## 代码生成流程

### 步骤 1：创建 OAuth 配置文件

创建 `funclip/auth/config.py`，包含所有 OAuth 参数（支持环境变量覆盖）。

### 步骤 2：生成 OAuth 路由

创建 `funclip/auth/oauth.py`，包含：
- `GET /api/auth/agentpit/sso` — SSO 入口端点
- `GET /api/auth/agentpit/callback` — OAuth 回调端点
- `GET /auth/sso/callback` — 前端 SSO 回调页
- `GET /api/auth/agentpit/login` — 弹窗式登录入口

### 步骤 3：生成 SSO 辅助脚本

创建 `funclip/auth/sso.py`，包含注入 Gradio 页面的 JS 脚本。

### 步骤 4：集成到 Gradio launch.py

修改 `launch.py`，挂载 OAuth 路由和 SSO 自动登录脚本。

---

## 输出结果

```
✅ AgentPit SSO 自动单点登录已生成！

已生成/修改文件：
- funclip/auth/__init__.py
- funclip/auth/config.py（OAuth 配置）
- funclip/auth/oauth.py（OAuth 路由 + SSO 入口 + 回调）
- funclip/auth/sso.py（SSO 辅助脚本）
- funclip/launch.py（集成 SSO）

功能说明：
- SSO 入口: GET /api/auth/agentpit/sso?returnUrl=/path
- OAuth 回调: GET /api/auth/agentpit/callback
- 登录按钮: agentpit 授权登陆
- 用户已在主站登录 → 自动静默完成授权
- 用户未在主站登录 → 跳转到登录页，显示错误提示
- 原有弹窗式登录完全保留，不受影响

下一步：
1. 配置环境变量（AGENTPIT_CLIENT_ID, AGENTPIT_CLIENT_SECRET 等）
2. pip install httpx PyJWT（安装依赖）
3. 重启 Gradio 服务
4. 测试：主站登录后，直接访问子应用验证自动登录
```
