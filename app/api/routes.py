"""API routes for the Change-Aware Auditor with robust input validation."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
import uuid
import logging
import hashlib

from app.config import settings
from app.api.security import rate_limit
from app.services.orchestrator import create_orchestrator
from app.services.diff_parser import DiffParser
from app.services.cache import InMemoryCache

router = APIRouter()
logger = logging.getLogger(__name__)
cache = InMemoryCache(max_entries=settings.cache_max_entries)

# Validation constants
MAX_LINES = 2000
MAX_LINE_LENGTH = 5000
MAX_FILES = 50
VALID_AUDITS = {"security", "quality", "performance", "best_practices"}
VALID_DEPTHS = {"quick", "standard", "deep"}


def validate_diff_content(diff: str) -> None:
    """Validate diff content for safety and sanity.

    Raises HTTPException on validation failure.
    """
    if not diff or not diff.strip():
        raise HTTPException(status_code=400, detail="Diff content cannot be empty")

    # Check total size
    if len(diff) > settings.max_diff_size:
        raise HTTPException(
            status_code=400,
            detail=f"Diff too large. Maximum size: {settings.max_diff_size} bytes"
        )

    # Check line count
    lines = diff.split('\n')
    if len(lines) > MAX_LINES:
        raise HTTPException(
            status_code=400,
            detail=f"Diff exceeds {MAX_LINES} lines limit. Found {len(lines)} lines."
        )

    # Check individual line lengths
    for i, line in enumerate(lines):
        if len(line) > MAX_LINE_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Line {i+1} exceeds {MAX_LINE_LENGTH} character limit"
            )


class AuditRequest(BaseModel):
    """Request model for code audit with validation."""
    diff: str = Field(..., description="Git diff content in unified format")
    audits: Optional[List[str]] = Field(
        default=None,
        description="Audit types to run: security, quality, performance, best_practices"
    )
    depth: Optional[str] = Field(
        default="standard",
        description="Analysis depth: quick, standard, deep"
    )

    @field_validator('audits')
    @classmethod
    def validate_audits(cls, v):
        if v is not None:
            invalid = set(v) - VALID_AUDITS
            if invalid:
                raise ValueError(
                    f"Invalid audit types: {', '.join(invalid)}. "
                    f"Valid options: {', '.join(VALID_AUDITS)}"
                )
        return v

    @field_validator('depth')
    @classmethod
    def validate_depth(cls, v):
        if v is not None and v not in VALID_DEPTHS:
            raise ValueError(
                f"Invalid depth: {v}. Valid options: {', '.join(VALID_DEPTHS)}"
            )
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "diff": "diff --git a/app.py b/app.py\\n@@ -1,5 +1,7 @@\\n+import os\\n password = 'secret123'\\n",
                "audits": ["security", "quality"],
                "depth": "standard"
            }
        }


class AuditResponse(BaseModel):
    """Response model for code audit."""
    audit_id: str
    status: str
    summary: Dict[str, Any]
    audits: Dict[str, Any]
    synthesis: Dict[str, Any]
    metadata: Dict[str, Any]


@router.post(
    "/audit/diff",
    response_model=AuditResponse,
    dependencies=[Depends(rate_limit)],
)
async def audit_diff(request: AuditRequest):
    """
    Audit a git diff with evidence-backed analysis.

    Limits:
    - Max diff size: 500KB
    - Max lines: 2000
    - Max files: 50
    - Max line length: 5000 chars
    """
    logger.info(f"Received audit request: depth={request.depth}, audits={request.audits}")

    # Validate diff content
    validate_diff_content(request.diff)

    # Check API key
    if not settings.akashml_api_key:
        logger.error("AkashML API key not configured")
        raise HTTPException(
            status_code=500,
            detail="AkashML API key not configured. Set AKASHML_API_KEY environment variable."
        )

    # Parse the diff
    parser = DiffParser()
    parsed_diff = parser.parse(request.diff)

    # Validate file count
    if parsed_diff.file_count > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Diff contains {parsed_diff.file_count} files. Maximum allowed: {MAX_FILES}"
        )

    # Validate we actually parsed something
    if parsed_diff.file_count == 0:
        logger.warning("Could not parse any files from the provided diff")
        raise HTTPException(
            status_code=400,
            detail="Could not parse any files from the provided diff. Ensure it's in unified diff format."
        )

    logger.info(
        f"Parsed diff: {parsed_diff.file_count} files, "
        f"+{parsed_diff.total_additions}/-{parsed_diff.total_deletions} lines, "
        f"languages: {list(parsed_diff.languages)}"
    )

    # Build cache key
    audits_key = ",".join(sorted(request.audits)) if request.audits else "all"
    cache_key_raw = f"{request.depth}|{audits_key}|{request.diff}"
    cache_key = hashlib.sha256(cache_key_raw.encode("utf-8")).hexdigest()

    audit_id = str(uuid.uuid4())

    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info("Cache hit for audit request")
        result = cached_result
        return AuditResponse(
            audit_id=audit_id,
            status="completed",
            summary={
                "overall_score": result["overall_score"],
                "risk_level": result["risk_level"],
                "total_findings": result["total_findings"],
                "critical_findings": result["critical_findings"]
            },
            audits=result["audits"],
            synthesis=result["synthesis"],
            metadata={
                "files_analyzed": parsed_diff.file_count,
                "lines_added": parsed_diff.total_additions,
                "lines_removed": parsed_diff.total_deletions,
                "languages": list(parsed_diff.languages)
            }
        )

    # Create orchestrator and run audit
    try:
        orchestrator = create_orchestrator(api_key=settings.akashml_api_key)

        try:
            result = await asyncio.wait_for(
                orchestrator.run_full_audit(
                    diff_content=request.diff,
                    selected_audits=request.audits,
                    depth=request.depth or "standard"
                ),
                timeout=300.0  # 5 minute timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Audit timed out after 300s: id={audit_id}")
            raise HTTPException(status_code=504, detail="Audit timed out. Try reducing diff size or using 'quick' depth.")

        await cache.set(cache_key, result, settings.cache_ttl_seconds)

        logger.info(
            f"Audit completed: id={audit_id}, score={result['overall_score']}, "
            f"findings={result['total_findings']}"
        )

        return AuditResponse(
            audit_id=audit_id,
            status="completed",
            summary={
                "overall_score": result["overall_score"],
                "risk_level": result["risk_level"],
                "total_findings": result["total_findings"],
                "critical_findings": result["critical_findings"]
            },
            audits=result["audits"],
            synthesis=result["synthesis"],
            metadata={
                "files_analyzed": parsed_diff.file_count,
                "lines_added": parsed_diff.total_additions,
                "lines_removed": parsed_diff.total_deletions,
                "languages": list(parsed_diff.languages)
            }
        )

    except ValueError as e:
        logger.error(f"Orchestrator initialization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Audit failed with unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)[:100]}")


@router.get("/models")
async def list_models():
    """List available LLM models."""
    from app.services.akashml_client import AkashMLClient
    return {
        "models": AkashMLClient.MODELS,
        "default": settings.default_model
    }


@router.get("/audits")
async def list_audits():
    """List available audit types."""
    return {
        "audits": [
            {
                "id": "security",
                "name": "Security Audit",
                "description": "Detect vulnerabilities (SQL injection, XSS, etc.)",
                "weight": 0.40
            },
            {
                "id": "quality",
                "name": "Code Quality",
                "description": "Assess code structure, naming, complexity",
                "weight": 0.25
            },
            {
                "id": "performance",
                "name": "Performance",
                "description": "Analyze algorithmic efficiency and resource usage",
                "weight": 0.20
            },
            {
                "id": "best_practices",
                "name": "Best Practices",
                "description": "Check error handling, documentation, testing patterns",
                "weight": 0.15
            }
        ]
    }
