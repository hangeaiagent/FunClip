"""AgentPit OAuth2 SSO endpoints for Gradio/FastAPI integration."""

import json
import time
import logging
from urllib.parse import urlencode, quote

import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from .config import (
    AGENTPIT_CLIENT_ID,
    AGENTPIT_CLIENT_SECRET,
    AGENTPIT_AUTHORIZE_URL,
    AGENTPIT_TOKEN_URL,
    AGENTPIT_USERINFO_URL,
    AGENTPIT_REDIRECT_URI,
    SESSION_SECRET,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_authorize_url(state: str) -> str:
    params = {
        "client_id": AGENTPIT_CLIENT_ID,
        "redirect_uri": AGENTPIT_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    return f"{AGENTPIT_AUTHORIZE_URL}?{urlencode(params)}"


@router.get("/api/auth/agentpit/sso")
async def sso_redirect(returnUrl: str = "/"):
    """SSO entry: redirect to AgentPit OAuth authorize page with sso: state prefix."""
    state = f"sso:{returnUrl}"
    return RedirectResponse(url=_build_authorize_url(state))


@router.get("/api/auth/agentpit/login")
async def login_redirect():
    """Popup login entry: redirect to AgentPit OAuth authorize page with popup state."""
    state = "popup"
    return RedirectResponse(url=_build_authorize_url(state))


@router.get("/api/auth/agentpit/callback")
async def oauth_callback(code: str, state: str = ""):
    """OAuth callback: exchange code for token, then route by state prefix."""
    try:
        # Exchange authorization code for access token
        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.post(
                AGENTPIT_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": AGENTPIT_REDIRECT_URI,
                    "client_id": AGENTPIT_CLIENT_ID,
                    "client_secret": AGENTPIT_CLIENT_SECRET,
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

        access_token = token_data.get("access_token")
        if not access_token:
            logger.error("No access_token in token response: %s", token_data)
            return HTMLResponse(
                content=_error_html("OAuth token exchange failed"),
                status_code=400,
            )

        # Fetch user info
        async with httpx.AsyncClient(timeout=30) as client:
            user_resp = await client.get(
                AGENTPIT_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            user_info = user_resp.json()

    except httpx.HTTPError as e:
        logger.error("OAuth HTTP error: %s", e)
        return HTMLResponse(
            content=_error_html(f"OAuth request failed: {e}"),
            status_code=502,
        )
    except Exception as e:
        logger.error("OAuth callback error: %s", e)
        return HTMLResponse(
            content=_error_html("Internal error during OAuth"),
            status_code=500,
        )

    # Generate JWT session token
    session_token = jwt.encode(
        {
            "sub": str(user_info.get("id", "")),
            "name": user_info.get("name", ""),
            "email": user_info.get("email", ""),
            "exp": int(time.time()) + 86400,  # 24h
        },
        SESSION_SECRET,
        algorithm="HS256",
    )

    encoded_user = quote(json.dumps(user_info, ensure_ascii=False))

    if state.startswith("sso:"):
        # SSO mode: full-page redirect via hash to avoid token in server logs
        return_url = state[4:]
        html = f"""<!DOCTYPE html>
<html><head><title>SSO Login</title></head>
<body>
<div style="text-align:center;margin-top:20vh;font-size:18px;">登录中...</div>
<script>
window.location.replace(
    '/auth/sso/callback?returnUrl={return_url}#token={session_token}&user={encoded_user}'
);
</script>
</body></html>"""
        return HTMLResponse(content=html)
    else:
        # Popup mode: postMessage back to opener
        html = f"""<!DOCTYPE html>
<html><head><title>OAuth Callback</title></head>
<body>
<div style="text-align:center;margin-top:20vh;font-size:18px;">授权成功，正在关闭...</div>
<script>
if (window.opener) {{
    window.opener.postMessage({{
        type: 'agentpit-oauth',
        token: '{session_token}',
        user: '{encoded_user}'
    }}, '*');
    window.close();
}} else {{
    localStorage.setItem('agentpit_token', '{session_token}');
    localStorage.setItem('agentpit_user', decodeURIComponent('{encoded_user}'));
    window.location.replace('/');
}}
</script>
</body></html>"""
        return HTMLResponse(content=html)


@router.get("/auth/sso/callback")
async def sso_callback_page():
    """Frontend SSO callback page: extract token from URL hash and save to localStorage."""
    html = """<!DOCTYPE html>
<html>
<head><title>SSO 登录中...</title></head>
<body>
<div style="text-align:center;margin-top:20vh;font-size:18px;">登录中...</div>
<script>
(function() {
    var hash = window.location.hash.substring(1);
    var params = new URLSearchParams(hash);
    var token = params.get('token');
    var userStr = params.get('user');
    var returnUrl = new URLSearchParams(window.location.search).get('returnUrl') || '/';

    // Clear sensitive info from URL immediately
    window.history.replaceState(null, '', window.location.pathname);

    if (token && userStr) {
        try {
            localStorage.setItem('agentpit_token', token);
            localStorage.setItem('agentpit_user', decodeURIComponent(userStr));
            // Clear SSO attempted flag on success
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


@router.get("/api/auth/agentpit/logout")
async def logout():
    """Logout: return JS that clears local storage and redirects to home."""
    html = """<!DOCTYPE html>
<html><head><title>Logout</title></head>
<body>
<script>
localStorage.removeItem('agentpit_token');
localStorage.removeItem('agentpit_user');
sessionStorage.removeItem('sso_attempted');
window.location.replace('/');
</script>
</body></html>"""
    return HTMLResponse(content=html)


def _error_html(message: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>Error</title></head>
<body>
<div style="text-align:center;margin-top:20vh;">
<h2>登录失败</h2>
<p>{message}</p>
<a href="/">返回首页</a>
</div>
</body></html>"""
