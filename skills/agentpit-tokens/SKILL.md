---
name: agentpit-tokens
description: 在 AgentPit 项目中生成 token 消耗上报接口，包含数据模型和 API 路由
user-invocable: true
---

# AgentPit Token 消耗上报接口生成

帮助开发者在 FunClip AgentPit 子应用中生成 token 消耗上报相关代码，供外部开发者的 Agent 应用在执行完成后将 token 消耗数据（消耗量、调用开始时间、结束时间）回传给 AgentPit 平台。

**工具使用：** 收集用户输入时使用 `AskUserQuestion` 工具。

---

## 前置条件检查

### 1. 环境检查

确认当前目录是 FunClip 项目根目录：

```
📂 当前工作目录: /path/to/FunClip

检查以下文件是否存在：
✅ funclip/launch.py（Gradio 入口）
✅ funclip/auth/config.py（OAuth 配置）
✅ funclip/auth/oauth.py（OAuth 路由）
✅ requirements.txt
```

如有缺失，提示用户先运行 `agentpit-sso` 技能完成基础 OAuth 集成。

### 2. 检查 state.json

- **`.agentpit/state.json` 不存在** → 自动创建，写入初始配置
- **存在且 `stage == "ready"`** → 询问：`已有生成记录，是否要重新生成 token 上报接口？`
- **其他情况** → 继续

---

## 用户输入收集

### 第一步：确认基础配置

展示默认配置并请用户确认：

```
📋 Token 上报接口配置

API 路径: POST /api/v1/tokens/report
认证方式: ApiKey Bearer Token（agp_xxx）
数据存储: SQLite（本地文件 token_usage.db）

关联信息:
- Agent ID（记录哪个 Agent 产生的消耗）
- Application ID（记录哪个应用上报的）
- User ID（ApiKey 所属用户）

确认以上配置是否正确？
```

### 第二步：收集额外字段需求

使用 `AskUserQuestion` 询问：

> 除了默认字段（tokensUsed、inputTokens、outputTokens、startedAt、endedAt），是否需要记录额外信息？
>
> 可选项：
> 1. `modelName` — AI 模型名称（如 gpt-4、claude-3）
> 2. `requestId` — 请求追踪 ID（用于关联外部系统日志）
> 3. `metadata` — 扩展 JSON 数据（自定义附加信息）
> 4. 不需要额外字段
> 5. 自定义字段（请描述）

---

## 代码生成规范

**⚠️ 以下规范必须严格遵守，不得违反：**

### 1. 数据模型 `TokenUsage`

使用 SQLite + SQLAlchemy 定义：

```python
# funclip/auth/models.py
from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DB_PATH = os.getenv("TOKEN_DB_PATH", "token_usage.db")
engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class TokenUsage(Base):
    __tablename__ = "apbase_token_usage"
    
    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, index=True)
    application_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    tokens_used = Column(Integer, nullable=False)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)
    model_name = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(engine)
```

**注意事项：**
- 表名必须使用 `apbase_` 前缀
- 根据用户在第二步的选择，增删可选字段（`model_name`、`request_id`、`metadata_json`）

### 2. API 路由 `POST /api/v1/tokens/report`

**文件位置：** `funclip/auth/token_report.py`

**认证逻辑（ApiKey Bearer Token）：**

```python
from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import uuid

router = APIRouter()

def ok(data):
    return JSONResponse({"success": True, "data": data})

def err(message, status=400):
    return JSONResponse({"success": False, "error": message}, status_code=status)

class TokenReportRequest(BaseModel):
    agentId: str
    tokensUsed: int
    inputTokens: Optional[int] = None
    outputTokens: Optional[int] = None
    startedAt: str  # ISO datetime
    endedAt: str    # ISO datetime
    modelName: Optional[str] = None
    requestId: Optional[str] = None
    metadata: Optional[dict] = None
    
    @field_validator("tokensUsed")
    @classmethod
    def tokens_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("tokensUsed 必须为正整数")
        return v

@router.post("/api/v1/tokens/report")
async def report_tokens(body: TokenReportRequest, authorization: str = Header(None)):
    # 1. ApiKey 认证
    if not authorization or not authorization.startswith("Bearer "):
        return err("缺少认证信息", 401)
    api_key = authorization[7:]
    
    # 验证 ApiKey（调用 AgentPit 平台验证或本地验证）
    # ... 根据实际 ApiKey 验证机制实现 ...
    
    # 2. 时间校验
    try:
        started = datetime.fromisoformat(body.startedAt.replace("Z", "+00:00"))
        ended = datetime.fromisoformat(body.endedAt.replace("Z", "+00:00"))
    except ValueError:
        return err("时间格式必须为 ISO 日期格式")
    
    if started >= ended:
        return err("startedAt 必须早于 endedAt")
    
    # 3. 写入数据库
    from .models import SessionLocal, TokenUsage
    db = SessionLocal()
    try:
        record = TokenUsage(
            id=str(uuid.uuid4()),
            agent_id=body.agentId,
            application_id="",  # 从 ApiKey 关联获取
            user_id="",         # 从 ApiKey 关联获取
            tokens_used=body.tokensUsed,
            input_tokens=body.inputTokens,
            output_tokens=body.outputTokens,
            started_at=started,
            ended_at=ended,
            model_name=body.modelName,
            request_id=body.requestId,
            metadata_json=body.metadata,
        )
        db.add(record)
        db.commit()
        
        return ok({
            "id": record.id,
            "agentId": record.agent_id,
            "tokensUsed": record.tokens_used,
            "startedAt": body.startedAt,
            "endedAt": body.endedAt,
            "createdAt": record.created_at.isoformat() if record.created_at else None,
        })
    except Exception as e:
        db.rollback()
        return err(f"服务器错误: {str(e)}", 500)
    finally:
        db.close()
```

**统一响应格式：**
- 成功：`{ success: true, data: { id, agentId, tokensUsed, startedAt, endedAt, createdAt } }`
- 失败：`{ success: false, error: "错误描述" }`

---

## 代码生成流程

### 步骤 1：新增数据模型

创建 `funclip/auth/models.py`，定义 `TokenUsage` 模型（SQLite + SQLAlchemy）。

### 步骤 2：生成 API 路由

创建 `funclip/auth/token_report.py`，使用上方完整代码模板。

根据用户在输入收集阶段的选择，调整 Pydantic schema 和数据库字段。

### 步骤 3：集成到 launch.py

在 `launch.py` 中挂载 token 上报路由：

```python
from auth.token_report import router as token_router
app.include_router(token_router)
```

### 步骤 4：更新 state.json

```json
{
  "version": "1.0",
  "stage": "ready",
  "feature_name": "agentpit-tokens",
  "feature_description": "Token 消耗上报接口，供外部开发者的 Agent 应用回传 token 消耗数据",
  "generated_files": [
    "funclip/auth/models.py",
    "funclip/auth/token_report.py",
    "funclip/launch.py（已更新）"
  ]
}
```

---

## 输出结果

```
✅ AgentPit Token 上报接口已生成！

已生成/修改文件：
- funclip/auth/models.py（TokenUsage 数据模型）
- funclip/auth/token_report.py（API 路由）
- funclip/launch.py（集成路由）

接口信息：
- 路径: POST /api/v1/tokens/report
- 认证: Authorization: Bearer agp_xxx（ApiKey）
- 请求体: { agentId, tokensUsed, startedAt, endedAt, ... }

下一步：
1. pip install sqlalchemy（如未安装）
2. 重启 Gradio 服务
3. 使用 ApiKey 调用 POST /api/v1/tokens/report 测试

请求示例：
curl -X POST http://localhost:7860/api/v1/tokens/report \
  -H "Authorization: Bearer agp_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "agentId": "agent_id_here",
    "tokensUsed": 1500,
    "inputTokens": 1000,
    "outputTokens": 500,
    "startedAt": "2025-01-01T00:00:00.000Z",
    "endedAt": "2025-01-01T00:00:05.000Z"
  }'
```
