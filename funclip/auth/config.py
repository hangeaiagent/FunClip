import os

# AgentPit OAuth2 Configuration
AGENTPIT_CLIENT_ID = os.getenv("AGENTPIT_CLIENT_ID", "cmnkgi132002o60t9pk3zpt8r")
AGENTPIT_CLIENT_SECRET = os.getenv("AGENTPIT_CLIENT_SECRET", "cmnkgi132002p60t9ssapujw6")
AGENTPIT_AUTHORIZE_URL = os.getenv("AGENTPIT_AUTHORIZE_URL", "https://app.agentpit.io/oauth/authorize")
AGENTPIT_TOKEN_URL = os.getenv("AGENTPIT_TOKEN_URL", "https://app.agentpit.io/oauth/token")
AGENTPIT_USERINFO_URL = os.getenv("AGENTPIT_USERINFO_URL", "https://app.agentpit.io/api/userinfo")
AGENTPIT_REDIRECT_URI = os.getenv("AGENTPIT_REDIRECT_URI", "https://funclip.agentpit.io/api/auth/agentpit/callback")
AGENTPIT_LOGIN_BUTTON_NAME = os.getenv("AGENTPIT_LOGIN_BUTTON_NAME", "agentpit 授权登陆")
SESSION_SECRET = os.getenv("SESSION_SECRET", "funclip-agentpit-session-secret")
