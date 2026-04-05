# Skill: 在 FunClip (Gradio) 项目中集成 Evolvr 用户反馈功能

> 适用于: FunClip (https://github.com/hangeaiagent/FunClip)
> 技术栈: Python + Gradio 6.x + FastAPI
> Evolvr API: https://evolvr.agentpit.io
> FunClip App ID: `858f129e-5872-4e44-93c8-0c13ac158317`

---

## 一、背景

Evolvr 是一个用户反馈驱动的 AI 自动修复闭环系统。用户在产品页面提交反馈后，Evolvr 会：

1. AI 分诊 — 自动分类问题类型和严重程度
2. 小 Bug — Claude Code 自动修复并创建 PR
3. 大需求 — 生成技术方案文档，通知开发者

本指南将在 FunClip 的 Gradio 界面中集成 Evolvr 反馈 Widget，使用户可以直接在产品界面提交问题反馈。

---

## 二、集成方案概览

FunClip 使用 Gradio (基于 FastAPI)，其前端由 Gradio 框架自动生成。集成方式有两种：

| 方案 | 方式 | 优点 | 缺点 |
|------|------|------|------|
| **A: JS Widget 注入** | 通过 Gradio `head` 参数注入 `<script>` | 零侵入，1 行代码 | 依赖 Evolvr CDN |
| **B: Gradio 原生组件** | 用 `gr.HTML` + `gr.Textbox` + `gr.Button` 构建 | 原生 UI 风格一致 | 代码量更多 |

**推荐方案 A**（最小改动），下面两种方案都会详细说明。

---

## 三、方案 A: JS Widget 注入 (推荐)

### 3.1 原理

Gradio 的 `gr.Blocks` 构造函数接受一个 `head` 参数，可以在 HTML `<head>` 中注入自定义 JS/CSS。我们利用这个参数注入 Evolvr 的反馈 Widget 脚本。

### 3.2 改动文件

仅需修改 **1 个文件**: `funclip/launch.py`

### 3.3 具体步骤

#### Step 1: 定义 Widget 脚本标签

在 `launch.py` 文件顶部（import 区域之后）添加常量：

```python
# ── Evolvr 用户反馈 Widget ──
EVOLVR_FEEDBACK_JS = """
<script
  src="https://evolvr.agentpit.io/widget/feedback-widget.js"
  data-api="https://evolvr.agentpit.io/api/feedback"
  data-app-id="858f129e-5872-4e44-93c8-0c13ac158317"
  async>
</script>
"""
```

#### Step 2: 注入到 Gradio 的 head 参数

找到 `gr.Blocks` 的构造位置（当前代码约第 174 行）：

```python
# 修改前:
with gr.Blocks(theme=theme, head=SSO_AUTO_LOGIN_JS + LOGIN_BUTTON_JS) as funclip_service:

# 修改后:
with gr.Blocks(theme=theme, head=SSO_AUTO_LOGIN_JS + LOGIN_BUTTON_JS + EVOLVR_FEEDBACK_JS) as funclip_service:
```

**完成！** 仅改动 2 处，增加约 10 行代码。

### 3.4 验证

1. 重启 FunClip 服务
2. 访问 https://funclip.agentpit.io
3. 页面右下角应出现紫色圆形反馈按钮
4. 点击按钮，输入反馈文字（>=5 字符），点击提交
5. 检查 Evolvr 后台是否收到反馈：

```bash
curl -s "https://evolvr.agentpit.io/api/admin/stats" \
  -H "x-api-key: evolvr-admin-2026" | python3 -m json.tool
```

### 3.5 可选: 传递用户身份

如果 FunClip 有用户登录系统（AgentPit SSO），可以将用户 ID 传给 Widget：

```python
# 通过 JS 动态设置 user-id（在 SSO 登录成功后）
EVOLVR_FEEDBACK_JS = """
<script>
  // 等待 SSO 登录完成后注入 Widget
  window.addEventListener('agentpit-login', function(e) {
    var s = document.createElement('script');
    s.src = 'https://evolvr.agentpit.io/widget/feedback-widget.js';
    s.setAttribute('data-api', 'https://evolvr.agentpit.io/api/feedback');
    s.setAttribute('data-app-id', '858f129e-5872-4e44-93c8-0c13ac158317');
    s.setAttribute('data-user-id', e.detail.userId || '');
    document.head.appendChild(s);
  });
</script>
"""
```

---

## 四、方案 B: Gradio 原生组件

如果不希望依赖外部 JS，可以用 Gradio 原生组件 + 直接调用 Evolvr API。

### 4.1 改动文件

仅需修改 **1 个文件**: `funclip/launch.py`

### 4.2 具体步骤

#### Step 1: 添加反馈提交函数

在 `launch.py` 的函数定义区域（约第 53 行之后）添加：

```python
import json
import urllib.request

EVOLVR_API = "https://evolvr.agentpit.io/api/feedback"
EVOLVR_APP_ID = "858f129e-5872-4e44-93c8-0c13ac158317"

def submit_feedback(description):
    """提交用户反馈到 Evolvr"""
    if not description or len(description.strip()) < 5:
        return "请至少输入 5 个字符"

    payload = json.dumps({
        "appId": EVOLVR_APP_ID,
        "description": description.strip(),
        "context": {
            "url": "https://funclip.agentpit.io",
            "source": "gradio-native",
            "recentErrors": [],
            "actionPath": [],
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        EVOLVR_API,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            feedback_id = result.get("feedbackId", "unknown")
            return f"已收到！反馈编号: {feedback_id[:8]}... 我们会尽快处理。"
    except Exception as e:
        logging.error(f"Evolvr feedback submit failed: {e}")
        return f"提交失败: {str(e)}"
```

#### Step 2: 在 Gradio 界面中添加反馈组件

在 `gr.Blocks` 内部的最后（所有 Tab 之后、`recog_button.click(...)` 之前）添加：

```python
        # ── 用户反馈 ──
        gr.Markdown("---")
        with gr.Row():
            with gr.Column(scale=3):
                feedback_input = gr.Textbox(
                    label="遇到问题？告诉我们",
                    placeholder="请描述您遇到的问题或建议...",
                    lines=3,
                    max_lines=5,
                )
            with gr.Column(scale=1, min_width=120):
                feedback_submit = gr.Button("提交反馈", variant="secondary")
                feedback_result = gr.Textbox(label="提交状态", interactive=False)

        feedback_submit.click(
            submit_feedback,
            inputs=[feedback_input],
            outputs=[feedback_result],
        )
```

### 4.3 验证

同方案 A 的验证步骤。

---

## 五、Evolvr API 参考

### 提交反馈

```
POST https://evolvr.agentpit.io/api/feedback
Content-Type: application/json
```

**请求体:**

```json
{
  "appId": "858f129e-5872-4e44-93c8-0c13ac158317",
  "description": "视频识别后点击裁剪没反应",
  "userId": "user-xxx",
  "context": {
    "url": "https://funclip.agentpit.io",
    "userAgent": "Mozilla/5.0 ...",
    "recentErrors": [
      {"message": "TypeError: ...", "source": "...", "line": 42}
    ],
    "actionPath": [
      {"tag": "BUTTON", "text": "裁剪", "time": 1712345678}
    ]
  },
  "screenshot": "data:image/jpeg;base64,..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `appId` | string | 是 | FunClip 的应用 ID |
| `description` | string | 是 | 用户描述 (>=5 字符, <=2000 字符) |
| `userId` | string | 否 | 用户标识 |
| `context` | object | 否 | 自动采集的上下文信息 |
| `screenshot` | string | 否 | Base64 编码的截图 |

**响应 (201):**

```json
{
  "feedbackId": "a1b2c3d4-...",
  "status": "submitted"
}
```

### 查询反馈状态

```
GET https://evolvr.agentpit.io/api/feedback/:id/status
```

**响应:**

```json
{
  "id": "a1b2c3d4-...",
  "status": "fixed",
  "userFacingNote": "此问题已修复，将在下次更新中生效",
  "updatedAt": "2026-04-05T10:00:00Z"
}
```

### 用户反馈列表

```
GET https://evolvr.agentpit.io/api/feedbacks?user_id=xxx
```

### 用户通知

```
GET https://evolvr.agentpit.io/api/notifications?user_id=xxx
POST https://evolvr.agentpit.io/api/notifications/:id/read
```

---

## 六、Widget 功能特性

JS Widget (方案 A) 自动提供以下能力：

| 功能 | 说明 |
|------|------|
| 浮动按钮 | 页面右下角紫色圆形按钮，点击展开反馈面板 |
| 自动采集上下文 | URL、浏览器信息、屏幕尺寸、控制台错误、操作路径 |
| 截图 | 可选，懒加载 html2canvas，截取当前页面 |
| 提交状态 | 提交后显示成功/失败提示 |
| Shadow DOM 隔离 | 样式不影响宿主页面 |
| 移动端适配 | 小屏自动调整面板宽度 |
| 零依赖 | < 5KB，无需安装任何 npm 包 |

### 程序化 API

```javascript
// 打开反馈面板
window.FeedbackWidget.open();

// 关闭反馈面板
window.FeedbackWidget.close();

// 程序化提交（如自动上报错误）
window.FeedbackWidget.submit('页面崩溃了', screenshotBase64);
```

---

## 七、完整代码 Diff (方案 A)

以下是方案 A 的最小改动 diff：

```diff
--- a/funclip/launch.py
+++ b/funclip/launch.py
@@ -14,6 +14,16 @@ from auth.token_report import router as token_router
 from auth.sso import SSO_AUTO_LOGIN_JS, LOGIN_BUTTON_JS
 from auth.config import AGENTPIT_LOGIN_BUTTON_NAME

+# ── Evolvr 用户反馈 Widget ──
+EVOLVR_FEEDBACK_JS = """
+<script
+  src="https://evolvr.agentpit.io/widget/feedback-widget.js"
+  data-api="https://evolvr.agentpit.io/api/feedback"
+  data-app-id="858f129e-5872-4e44-93c8-0c13ac158317"
+  async>
+</script>
+"""
+
 if __name__ == "__main__":
     parser = argparse.ArgumentParser(description='argparse testing')
@@ -171,7 +181,7 @@ if __name__ == "__main__":

     # gradio interface
     theme = gr.Theme.load("funclip/utils/theme.json")
-    with gr.Blocks(theme=theme, head=SSO_AUTO_LOGIN_JS + LOGIN_BUTTON_JS) as funclip_service:
+    with gr.Blocks(theme=theme, head=SSO_AUTO_LOGIN_JS + LOGIN_BUTTON_JS + EVOLVR_FEEDBACK_JS) as funclip_service:
         gr.Markdown(top_md_1)
```

---

## 八、部署流程

集成代码合并到 `main` 分支后，在 FunClip 服务器上执行部署：

```bash
# SSH 到 FunClip 服务器
ssh -i ~/.ssh/id_rsa_google_longterm a1@34.21.190.240

# 拉取最新代码
cd /opt/funclip
git pull origin main

# 重启服务
kill $(cat funclip.pid 2>/dev/null) 2>/dev/null
sleep 2
source venv/bin/activate
nohup python3 FunClip/launch.py --listen --port 7860 > funclip.log 2>&1 &
echo $! > funclip.pid

# 验证
sleep 3
curl -sf http://127.0.0.1:7860 > /dev/null && echo "FunClip 启动成功" || echo "启动失败"
```

或通过 Evolvr 自动部署（需先开启 autoDeploy）：

```bash
curl -X PUT https://evolvr.agentpit.io/api/admin/apps/858f129e-5872-4e44-93c8-0c13ac158317 \
  -H "Content-Type: application/json" \
  -H "x-api-key: evolvr-admin-2026" \
  -d '{"autoDeploy": true}'
```

---

## 九、测试验证清单

集成完成后，按以下清单验证：

- [ ] 访问 https://funclip.agentpit.io，右下角出现紫色反馈按钮
- [ ] 点击按钮，面板展开，可输入文字
- [ ] 输入 < 5 字符，提示字数不足
- [ ] 输入 >= 5 字符，点击提交，显示成功
- [ ] 截图功能：点击截图按钮，显示"已截图"
- [ ] 提交后 3 秒面板自动关闭
- [ ] Evolvr 后台收到反馈：
  ```bash
  curl -s "https://evolvr.agentpit.io/api/admin/stats" \
    -H "x-api-key: evolvr-admin-2026"
  ```
- [ ] Worker 自动处理反馈（AI 分诊 → 路由）
- [ ] 查看反馈状态：
  ```bash
  curl -s "https://evolvr.agentpit.io/api/feedback/<feedbackId>/status"
  ```

---

## 十、故障排查

| 问题 | 排查方法 |
|------|---------|
| 反馈按钮不显示 | 浏览器 F12 Console 检查是否有 JS 加载错误 |
| 提交返回 CORS 错误 | Evolvr `.env` 中 `CORS_ORIGINS=*` 已设置 |
| 提交返回 400 | 检查 `appId` 是否正确: `858f129e-5872-4e44-93c8-0c13ac158317` |
| 提交返回 500 | 查看 Evolvr 日志: `pm2 logs self-iteration-api --lines 50` |
| Widget 样式与页面冲突 | Widget 使用 Shadow DOM 隔离，不应发生；如果出现，检查页面是否有 `all: initial` 全局覆盖 |
| 截图功能失败 | html2canvas CDN 可能被墙，可改用本地托管 |

---

## 附录: 关键配置参数

| 参数 | 值 |
|------|---|
| Evolvr API | `https://evolvr.agentpit.io/api/feedback` |
| Widget JS | `https://evolvr.agentpit.io/widget/feedback-widget.js` |
| FunClip App ID | `858f129e-5872-4e44-93c8-0c13ac158317` |
| Evolvr Admin Key | `evolvr-admin-2026` |
| FunClip 域名 | `funclip.agentpit.io` |
| FunClip 服务器 | `34.21.190.240` (a1) |
| Evolvr 服务器 | `34.126.122.183` (a1) |
