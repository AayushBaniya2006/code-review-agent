"""Evidence-first orchestrator for multi-audit analysis."""
from typing import Dict, List, Any, Optional
import asyncio
import json
import logging

from app.services.akashml_client import AkashMLClient
from app.config import settings
from app.prompts.templates import AUDIT_PROMPTS, SYNTHESIS_PROMPT

logger = logging.getLogger(__name__)


class AuditOrchestrator:
    """Orchestrates multiple audit passes with evidence-backed outputs."""

    # Weights for overall score calculation
    AUDIT_WEIGHTS = {
        "security": 0.40,
        "quality": 0.25,
        "performance": 0.20,
        "best_practices": 0.15
    }

    def __init__(self, akashml_client: AkashMLClient):
        self.client = akashml_client

    async def run_full_audit(
        self,
        diff_content: str,
        selected_audits: Optional[List[str]] = None,
        depth: str = "standard"
    ) -> Dict[str, Any]:
        """Run comprehensive audit with all selected auditors."""
        audits_to_run = selected_audits or list(AUDIT_PROMPTS.keys())
        diff_chunks = self._chunk_diff(diff_content)
        if len(diff_chunks) > 1:
            logger.info(f"Chunking diff into {len(diff_chunks)} parts for analysis")

        audit_results = {}
        all_findings = []

        # Run each audit
        for audit_type in audits_to_run:
            if audit_type not in AUDIT_PROMPTS:
                continue

            if len(diff_chunks) > 1:
                result = await self._run_audit_on_chunks(audit_type, diff_chunks, depth)
            else:
                result = await self._run_single_audit(audit_type, diff_content, depth)
            audit_results[audit_type] = result

            # Collect all findings
            for finding in result.get("findings", []):
                finding["audit_type"] = audit_type
                all_findings.append(finding)

        # Calculate overall score
        overall_score = self._calculate_overall_score(audit_results)

        # Determine risk level
        risk_level = self._determine_risk_level(overall_score, all_findings)

        # Generate synthesis
        synthesis = await self._synthesize_findings(audit_results, depth)

        return {
            "overall_score": overall_score,
            "risk_level": risk_level,
            "audits": audit_results,
            "synthesis": synthesis,
            "total_findings": len(all_findings),
            "critical_findings": sum(1 for f in all_findings if f.get("severity") == "critical")
        }

    async def _run_single_audit(
        self,
        audit_type: str,
        diff_content: str,
        depth: str,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """Run a single audit type with retry logic for transient failures."""
        prompt_template = AUDIT_PROMPTS.get(audit_type)
        if not prompt_template:
            return {"error": f"Unknown audit type: {audit_type}", "findings": [], "score": None}

        prompt = prompt_template.format(diff_content=diff_content)

        last_error = None
        for attempt in range(max_retries + 1):
            response = self.client.analyze(
                prompt=prompt,
                depth=depth,
                temperature=0.1
            )

            # If successful, break out of retry loop
            if response.get("success", False):
                break

            # If error is not retryable, don't retry
            if not response.get("retryable", False):
                last_error = response.get("error", "Unknown error")
                logger.warning(f"Audit {audit_type} failed (non-retryable): {last_error}")
                return {
                    "error": last_error,
                    "findings": [],
                    "score": None,
                    "reasoning_steps": []
                }

            # Retryable error - retry with exponential backoff (non-blocking)
            last_error = response.get("error", "Unknown error")
            if attempt < max_retries:
                delay = 2 * (2 ** attempt)  # 2s, 4s
                logger.info(
                    f"Audit {audit_type} attempt {attempt + 1} failed: {last_error}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)

        # Check if we exhausted retries
        if response.get("error"):
            logger.error(f"Audit {audit_type} failed after {max_retries + 1} attempts: {last_error}")
            return {
                "error": last_error or response.get("error"),
                "findings": [],
                "score": None,
                "reasoning_steps": []
            }

        # Parse the JSON response
        parsed = self.client.parse_json_response(response.get("content", ""))

        # Handle parse failure - score should be None, not a default value
        score = parsed.get("score")
        if score is None and not parsed.get("parse_success", False):
            logger.warning(f"Audit {audit_type} returned unparseable response")
            parse_error = parsed.get("error", "Failed to parse model response")
        else:
            parse_error = None

        return {
            "score": score,
            "findings": parsed.get("findings", []),
            "reasoning_steps": parsed.get("reasoning_steps", []),
            "raw_content": parsed.get("raw_content"),
            "model_used": response.get("model"),
            "tokens": response.get("usage", {}),
            "parse_success": parsed.get("parse_success", False),
            "parse_error": parse_error
        }

    async def _run_audit_on_chunks(
        self,
        audit_type: str,
        diff_chunks: List[str],
        depth: str
    ) -> Dict[str, Any]:
        """Run an audit across multiple diff chunks and merge results."""
        merged_findings: List[Dict[str, Any]] = []
        scores: List[int] = []
        parse_success = True
        errors = []

        for chunk in diff_chunks:
            result = await self._run_single_audit(audit_type, chunk, depth)
            merged_findings.extend(result.get("findings", []))
            if result.get("score") is not None:
                scores.append(result.get("score"))
            if result.get("parse_success") is False:
                parse_success = False
            if result.get("error"):
                errors.append(result.get("error"))

        merged_score = int(sum(scores) / len(scores)) if scores else None
        error_message = "; ".join(errors) if errors else None

        return {
            "score": merged_score,
            "findings": merged_findings,
            "reasoning_steps": [],
            "raw_content": None,
            "model_used": None,
            "tokens": {},
            "parse_success": parse_success,
            "parse_error": None if parse_success else "One or more chunks failed to parse",
            "error": error_message
        }

    def _chunk_diff(self, diff_content: str) -> List[str]:
        """Split diff into per-file chunks to keep prompt sizes manageable."""
        max_chunk_size = settings.chunk_size_chars
        if max_chunk_size <= 0 or len(diff_content) <= max_chunk_size:
            return [diff_content]

        chunks = []
        current = []

        for line in diff_content.split('\n'):
            if line.startswith('diff --git ') and current:
                chunks.append('\n'.join(current))
                current = [line]
            else:
                current.append(line)

        if current:
            chunks.append('\n'.join(current))

        return chunks if chunks else [diff_content]

    async def _synthesize_findings(
        self,
        audit_results: Dict[str, Any],
        depth: str
    ) -> Dict[str, Any]:
        """Synthesize all findings into executive summary."""
        summary_data = {}
        for audit_type, result in audit_results.items():
            summary_data[audit_type] = {
                "score": result.get("score") if result.get("score") is not None else 50,
                "finding_count": len(result.get("findings", [])),
                "findings": result.get("findings", [])[:3]
            }

        prompt = SYNTHESIS_PROMPT.format(
            audit_results=json.dumps(summary_data, indent=2)
        )

        response = self.client.analyze(
            prompt=prompt,
            depth=depth,
            temperature=0.2
        )

        if response.get("error"):
            fallback_verdict = self._compute_fallback_verdict(audit_results)
            logger.warning(f"Synthesis failed, using fallback verdict: {fallback_verdict}")
            return {
                "executive_summary": "Analysis complete. Review individual audit results.",
                "verdict": fallback_verdict,
                "critical_issues": self._extract_critical_issues(audit_results),
                "recommendations": [],
                "error": response["error"]
            }

        parsed = self.client.parse_json_response(response.get("content", ""))

        if not parsed.get("parse_success", False):
            fallback_verdict = self._compute_fallback_verdict(audit_results)
            logger.warning(f"Synthesis parse failed, using fallback verdict: {fallback_verdict}")
            return {
                "executive_summary": "Analysis complete. Review individual audit results.",
                "verdict": fallback_verdict,
                "critical_issues": self._extract_critical_issues(audit_results),
                "recommendations": [],
                "error": parsed.get("error", "Failed to parse synthesis response")
            }

        return {
            "executive_summary": parsed.get("executive_summary", ""),
            "critical_issues": parsed.get("critical_issues", []),
            "recommendations": parsed.get("recommendations", []),
            "verdict": parsed.get("verdict", "APPROVE_WITH_CHANGES")
        }

    def _compute_fallback_verdict(self, audit_results: Dict[str, Any]) -> str:
        """Compute verdict from individual audit scores when synthesis fails."""
        overall = self._calculate_overall_score(audit_results)

        has_critical = any(
            f.get("severity") == "critical"
            for audit in audit_results.values()
            for f in audit.get("findings", [])
        )

        high_count = sum(
            1 for audit in audit_results.values()
            for f in audit.get("findings", [])
            if f.get("severity") == "high"
        )

        if has_critical or overall < 40:
            return "REQUEST_CHANGES"
        if overall < 60 or high_count >= 3:
            return "APPROVE_WITH_CHANGES"
        if overall < 80:
            return "APPROVE_WITH_CHANGES"
        return "APPROVE"

    def _extract_critical_issues(self, audit_results: Dict[str, Any]) -> List[str]:
        """Extract critical issues from audit results for fallback synthesis."""
        critical_issues = []
        for audit_type, result in audit_results.items():
            for finding in result.get("findings", []):
                if finding.get("severity") in ("critical", "high"):
                    title = finding.get("title") or finding.get("type") or "Issue"
                    desc = finding.get("description", "")[:100]
                    critical_issues.append(f"[{audit_type}] {title}: {desc}")
        return critical_issues[:5]

    def _calculate_overall_score(self, audit_results: Dict[str, Any]) -> int:
        """Calculate weighted overall score."""
        total_weight = 0
        weighted_sum = 0

        for audit_type, weight in self.AUDIT_WEIGHTS.items():
            if audit_type in audit_results:
                result = audit_results[audit_type]
                score = result.get("score")
                if score is not None and not result.get("error"):
                    weighted_sum += score * weight
                    total_weight += weight

        if total_weight == 0:
            logger.warning("No valid audit scores available, returning 50")
            return 50

        return int(weighted_sum / total_weight)

    def _determine_risk_level(
        self,
        overall_score: int,
        findings: List[Dict[str, Any]]
    ) -> str:
        """Determine risk level based on score and findings."""
        critical_count = sum(1 for f in findings if f.get("severity") == "critical")
        high_count = sum(1 for f in findings if f.get("severity") == "high")

        if critical_count > 0:
            return "critical"
        if overall_score < 50 or high_count >= 3:
            return "high"
        if overall_score < 70 or high_count > 0:
            return "medium"
        return "low"


def create_orchestrator(api_key: str = None) -> AuditOrchestrator:
    """Factory function to create orchestrator with client."""
    client = AkashMLClient(api_key=api_key)
    return AuditOrchestrator(client)
