"""AkashML API Client - OpenAI-compatible interface with robust error handling."""
from openai import OpenAI
from openai import (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    AuthenticationError,
    APIError
)
from typing import Optional, Dict, Any
import os
import json
import re
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class AkashMLClient:
    """OpenAI-compatible client for AkashML inference with proper error handling."""

    TIMEOUT = 60.0  # 60 second timeout
    MAX_RESPONSE_SIZE = 100000  # 100KB max response to prevent memory exhaustion

    # Available models on AkashML (as of Jan 2026)
    MODELS = {
        "deep": "deepseek-ai/DeepSeek-V3.2",
        "standard": "meta-llama/Llama-3.3-70B-Instruct",
        "quick": "Qwen/Qwen3-30B-A3B"
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("AKASHML_API_KEY") or settings.akashml_api_key
        if not self.api_key:
            raise ValueError("AKASHML_API_KEY is required")

        base_url = settings.akashml_base_url or "https://api.akashml.com/v1"
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=self.TIMEOUT
        )
        logger.info(f"AkashML client initialized with {self.TIMEOUT}s timeout")

    def analyze(
        self,
        prompt: str,
        system_prompt: str = None,
        depth: str = "standard",
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Execute analysis with AkashML with proper error handling."""
        model = self.MODELS.get(depth) or settings.default_model or self.MODELS["standard"]

        if system_prompt is None:
            system_prompt = self._get_default_system_prompt()

        logger.info(f"Starting analysis with model={model}, depth={depth}")
        logger.debug(f"Prompt length: {len(prompt)} chars")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content if response.choices else None
            if not content:
                logger.warning("Empty response from model")
                return {
                    "content": None,
                    "error": "Model returned empty response",
                    "error_type": "empty_response",
                    "model": model,
                    "retryable": True,
                    "success": False
                }

            # Truncate oversized responses to prevent memory issues
            if len(content) > self.MAX_RESPONSE_SIZE:
                logger.warning(f"Response too large ({len(content)} chars), truncating to {self.MAX_RESPONSE_SIZE}")
                content = content[:self.MAX_RESPONSE_SIZE]

            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0
            }

            logger.info(f"Analysis completed: {usage['completion_tokens']} tokens generated")

            return {
                "content": content,
                "model": model,
                "usage": usage,
                "success": True
            }

        except APITimeoutError as e:
            logger.error(f"AkashML API timeout after {self.TIMEOUT}s")
            return {
                "content": None,
                "error": "API request timed out. Please try again.",
                "error_type": "timeout",
                "model": model,
                "retryable": True,
                "success": False
            }

        except RateLimitError as e:
            logger.warning(f"Rate limited by AkashML: {e}")
            return {
                "content": None,
                "error": "Rate limited. Please wait before retrying.",
                "error_type": "rate_limit",
                "model": model,
                "retryable": True,
                "success": False
            }

        except AuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            return {
                "content": None,
                "error": "Invalid API key. Check AKASHML_API_KEY configuration.",
                "error_type": "auth",
                "model": model,
                "retryable": False,
                "success": False
            }

        except APIConnectionError as e:
            logger.error(f"Connection failed: {e}")
            return {
                "content": None,
                "error": "Cannot connect to AkashML API. Check network.",
                "error_type": "connection",
                "model": model,
                "retryable": True,
                "success": False
            }

        except APIError as e:
            logger.error(f"API error: {e.status_code} - {e}")
            return {
                "content": None,
                "error": f"API error ({e.status_code}): {str(e)[:100]}",
                "error_type": "api_error",
                "model": model,
                "retryable": e.status_code >= 500,  # Retry on server errors
                "success": False
            }

        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            return {
                "content": None,
                "error": f"Unexpected error: {str(e)[:100]}",
                "error_type": "unknown",
                "model": model,
                "retryable": False,
                "success": False
            }

    def _get_default_system_prompt(self) -> str:
        return """You are an expert code auditor specializing in:
- Security vulnerability detection (OWASP Top 10, CWE patterns)
- Code quality assessment
- Performance analysis
- Best practices review

Provide evidence-backed findings with specific line numbers, clear explanations,
and actionable fixes. Do not include chain-of-thought; output only final
answers in valid JSON when requested."""

    def parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from LLM response with robust error handling.

        Returns score: None on parse failure (not a default value) so callers
        can distinguish between a legitimate score and a parse failure.
        """
        if not content:
            logger.warning("Empty response from model")
            return {
                "error": "Empty response from model",
                "findings": [],
                "score": None,
                "parse_success": False
            }

        # Detect HTML error pages (indicates API issue, not valid response)
        content_start = content.strip()[:100].lower()
        if content_start.startswith('<!doctype') or content_start.startswith('<html'):
            logger.error("Received HTML instead of JSON from API")
            return {
                "error": "API returned HTML error page instead of JSON",
                "findings": [],
                "score": None,
                "parse_success": False
            }

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                result["parse_success"] = True
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed in markdown block: {e}")

        # Try direct JSON parse
        try:
            result = json.loads(content)
            result["parse_success"] = True
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Cannot parse LLM response as JSON: {e}")
            logger.debug(f"Raw content preview: {content[:300]}")
            return {
                "error": f"Invalid JSON response: {str(e)[:50]}",
                "findings": [],
                "score": None,
                "parse_success": False,
                "raw_preview": content[:500]
            }

    def fix_json(self, malformed_content: str) -> Dict[str, Any]:
        """
        Attempt to fix malformed JSON using LLM.
        Returns { success: bool, fixed_json: dict | None, error: str | None }
        """
        if not malformed_content or len(malformed_content.strip()) < 10:
            return {"success": False, "error": "Content too short to repair"}

        from app.prompts.templates import FIX_JSON_PROMPT

        prompt = FIX_JSON_PROMPT.format(content=malformed_content[:2000])

        response = self.analyze(
            prompt=prompt,
            temperature=0.0,
            max_tokens=2048
        )

        if response.get("error") or not response.get("success"):
            return {
                "success": False,
                "error": response.get("error", "LLM call failed"),
                "usage": response.get("usage")
            }

        content = response.get("content", "")
        parsed = self.parse_json_response(content)

        if parsed.get("parse_success"):
            return {
                "success": True,
                "fixed_json": parsed,
                "usage": response.get("usage")
            }

        return {
            "success": False,
            "error": "Repair attempt also produced invalid JSON",
            "raw_repair": content[:500],
            "usage": response.get("usage")
        }
