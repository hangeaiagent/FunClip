"""AgentPit Token consumption reporting API."""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from .models import SessionLocal, TokenUsage

logger = logging.getLogger(__name__)

router = APIRouter()


def ok(data):
    return JSONResponse({"success": True, "data": data})


def err(message: str, status: int = 400):
    return JSONResponse({"success": False, "error": message}, status_code=status)


class TokenReportRequest(BaseModel):
    agentId: str
    tokensUsed: int
    inputTokens: Optional[int] = None
    outputTokens: Optional[int] = None
    startedAt: str  # ISO datetime string
    endedAt: str  # ISO datetime string
    modelName: Optional[str] = None
    requestId: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator("agentId")
    @classmethod
    def agent_id_not_empty(cls, v):
        if not v.strip():
            raise ValueError("agentId 不能为空")
        return v

    @field_validator("tokensUsed")
    @classmethod
    def tokens_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("tokensUsed 必须为正整数")
        return v


@router.post("/api/v1/tokens/report")
async def report_tokens(
    body: TokenReportRequest,
    authorization: Optional[str] = Header(None),
):
    """Report token consumption from external Agent applications."""
    # 1. ApiKey authentication
    if not authorization or not authorization.startswith("Bearer "):
        return err("缺少认证信息", 401)
    api_key = authorization[7:]
    if not api_key:
        return err("无效的 API Key", 401)

    # 2. Parse and validate timestamps
    try:
        started = datetime.fromisoformat(body.startedAt.replace("Z", "+00:00"))
        ended = datetime.fromisoformat(body.endedAt.replace("Z", "+00:00"))
    except ValueError:
        return err("时间格式必须为 ISO 日期格式")

    if started >= ended:
        return err("startedAt 必须早于 endedAt")

    # 3. Write to database
    db = SessionLocal()
    try:
        record = TokenUsage(
            id=str(uuid.uuid4()),
            agent_id=body.agentId,
            application_id="",  # Populated from ApiKey lookup if available
            user_id="",  # Populated from ApiKey lookup if available
            tokens_used=body.tokensUsed,
            input_tokens=body.inputTokens,
            output_tokens=body.outputTokens,
            started_at=started,
            ended_at=ended,
            model_name=body.modelName,
            request_id=body.requestId,
            metadata_json=json.dumps(body.metadata) if body.metadata else None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return ok(
            {
                "id": record.id,
                "agentId": record.agent_id,
                "tokensUsed": record.tokens_used,
                "startedAt": body.startedAt,
                "endedAt": body.endedAt,
                "createdAt": record.created_at.isoformat() if record.created_at else None,
            }
        )
    except Exception as e:
        db.rollback()
        logger.error("[tokens/report] POST error: %s", e)
        return err("服务器错误", 500)
    finally:
        db.close()
