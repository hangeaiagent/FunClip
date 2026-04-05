"""SSO auto-login JavaScript injection for Gradio pages."""

SSO_AUTO_LOGIN_JS = """
<script>
(function() {
    var SSO_KEY = 'sso_attempted';

    function shouldAutoSso() {
        var path = window.location.pathname;
        if (path.startsWith('/auth/sso/callback')) return false;
        if (path === '/login') return false;
        if (new URLSearchParams(window.location.search).has('sso_error')) return false;
        if (sessionStorage.getItem(SSO_KEY)) return false;
        if (localStorage.getItem('agentpit_token')) return false;
        return true;
    }

    function markSsoAttempted() {
        sessionStorage.setItem(SSO_KEY, 'true');
    }

    // Auto-trigger SSO if conditions are met
    if (shouldAutoSso()) {
        markSsoAttempted();
        var returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = '/api/auth/agentpit/sso?returnUrl=' + returnUrl;
    }
})();
</script>
"""

LOGIN_BUTTON_JS = """
<script>
function agentpitLogin() {
    var w = 600, h = 700;
    var left = (screen.width - w) / 2;
    var top = (screen.height - h) / 2;
    var popup = window.open(
        '/api/auth/agentpit/login',
        'agentpit_oauth',
        'width=' + w + ',height=' + h + ',left=' + left + ',top=' + top
    );

    window.addEventListener('message', function handler(event) {
        if (event.data && event.data.type === 'agentpit-oauth') {
            localStorage.setItem('agentpit_token', event.data.token);
            localStorage.setItem('agentpit_user', decodeURIComponent(event.data.user));
            sessionStorage.removeItem('sso_attempted');
            window.removeEventListener('message', handler);
            window.location.reload();
        }
    });
}
</script>
"""
