# Change-Aware Auditor

> **DEMO NOT FUNCTIONAL** - This project was built during a 1-day hackathon
> (AI Agent Build Night with AkashML, January 2026). The AkashML API credits
> have expired, so the live demo no longer works. To run this yourself, you'll
> need to provide your own AkashML API key.

An AI that audits git diffs for security and regression risk. Paste a diff
and get an evidence-backed analysis of what could break or be exploited --
before you merge.

---

## What This Project Is About

Change-Aware Auditor is a focused system that evaluates *code changes* rather
than entire repositories, with a bias toward failure and exploit risk. It
takes a unified git diff and:

- Parses the diff into structured metadata (files, additions, deletions).
- Runs multiple audit passes with an LLM via AkashML's OpenAI-compatible API.
- Produces evidence-backed findings with line references and fix suggestions.
- Synthesizes a verdict and risk level for the change.
- Displays results in a simple web UI for live demos.

The central idea: reviewers care about the *delta*. The system concentrates on
the diff to keep prompts small, speed up inference, and provide actionable
feedback.

---

## Current Progress (As-Is)

**Implemented**
- FastAPI backend with a health endpoint and a single audit API.
- AkashML client using the OpenAI SDK with a configurable model per depth.
- Diff parser to extract file counts, additions/deletions, and languages.
- Multi-audit orchestration with weighted scoring and synthesis.
- Web UI for diff input, audit options, and results display.
- Dockerfile and Akash SDL (deploy.yaml) for containerized deployment.
- Findings include line numbers, descriptions, and fix suggestions (model-driven).
- Basic rate limiting on the audit endpoint.
- Optional patch and test suggestions when the model provides them.

**Known Gaps / TODO**
- No shared cache or queueing for repeated requests (in-memory cache only).
- Limited test coverage (core parsing + cache + orchestrator tests exist; no API/UX tests).
- Limited error visibility if the model fails JSON formatting.
- Chunking is per-file only; very large single-file diffs can still exceed context.
- Patch/test suggestions are advisory and not applied automatically.

---

## Demo Flow (Recommended)

1. Paste a diff that introduces a subtle auth or injection bug.
2. Select audit types and depth.
3. Click "Run Audit" and review evidence-backed findings.
4. Show the risk score, verdict, and per-category findings.
5. Walk through severity-coded findings with line references and suggested fixes.

---

## Architecture Overview

```
Browser UI
  |
  |  POST /api/v1/audit/diff
  v
FastAPI (app/main.py)
  |
  |  parse diff + build prompts
  v
AuditOrchestrator (app/services/orchestrator.py)
  |
  |  LLM calls (security, quality, performance, best_practices)
  v
AkashML Client (app/services/akashml_client.py)
  |
  v
AkashML Inference API
```

---

## Key Features

- **Diff-Risk Score** - Rates how dangerous a change is (LOW -> CRITICAL)
- **Exploit Detection** - Finds auth bypasses, injections, and unsafe input paths
- **Evidence-Backed Findings** - Each issue cites exact diff lines with suggestions
- **Patch/Test Suggestions** - Model-generated patch and test snippets when available
- **Executive Synthesis** - Combines findings into actionable verdict

---

## Project Structure

```
code-review-agent/
  app/
    api/routes.py              API endpoints
    config.py                  env configuration
    main.py                    FastAPI app setup
    prompts/templates.py       LLM prompts
    services/
      akashml_client.py        AkashML client wrapper
      diff_parser.py           unified diff parser
      orchestrator.py          audit runner + synthesis
  static/app.js                frontend logic
  templates/index.html         frontend UI
  Dockerfile                   container image
  deploy.yaml                  Akash SDL
  docker-compose.yml           local docker compose
  requirements.txt             Python deps
  test_request.json            sample request payload
```

---

## Quick Start (Local)

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AKASHML_API_KEY="your-api-key"

# Run the server
uvicorn app.main:app --reload

# Open http://localhost:8000
```

---

## Docker Usage

```bash
# Build
docker build -t change-aware-auditor .

# Run
docker run -p 8000:8000 -e AKASHML_API_KEY="your-key" change-aware-auditor
```

---

## Docker Compose

```bash
export AKASHML_API_KEY="your-key"
docker compose up --build
```

---

## API

### POST /api/v1/audit/diff

Payload:
```json
{
  "diff": "diff --git a/app.py b/app.py\n@@ -1,5 +1,7 @@\n+import os\n",
  "audits": ["security", "quality", "performance", "best_practices"],
  "depth": "standard"
}
```

Response (shape):
```json
{
  "audit_id": "uuid",
  "status": "completed",
  "summary": {
    "overall_score": 72,
    "risk_level": "medium",
    "total_findings": 4,
    "critical_findings": 1
  },
  "audits": {
    "security": { "score": 68, "findings": [] },
    "quality": { "score": 80, "findings": [] }
  },
  "synthesis": {
    "executive_summary": "...",
    "critical_issues": [],
    "recommendations": [],
    "verdict": "APPROVE_WITH_CHANGES"
  },
  "metadata": {
    "files_analyzed": 2,
    "lines_added": 12,
    "lines_removed": 4,
    "languages": ["python"]
  }
}
```

### GET /api/v1/models
Returns available depth-to-model mappings and the default model.

### GET /api/v1/audits
Returns supported audit types with weights.

### GET /health
Basic health check for container and Akash readiness.

---

## Configuration

Environment variables (see `app/config.py`):

- `AKASHML_API_KEY` (required): API key for AkashML inference.
- `ENVIRONMENT` (optional): `development` or `production`.
- `LOG_LEVEL` (optional): Logging verbosity.
- `MAX_DIFF_SIZE` (optional): Max diff size in bytes (defaults to 500000).
- `RATE_LIMIT_PER_MINUTE` (optional): Per-client request limit (default: 60).
- `TRUST_PROXY_HEADERS` (optional): Honor `X-Forwarded-For` for rate limits (default: false).
- `CACHE_TTL_SECONDS` (optional): Cache TTL for identical audits (default: 300).
- `CACHE_MAX_ENTRIES` (optional): Max cached entries in memory (default: 256).
- `CHUNK_SIZE_CHARS` (optional): Chunk diffs by file when larger than this size (default: 120000).
- `CORS_ALLOWED_ORIGINS` (optional): Comma-separated origins or `*` for all (default: localhost only).
- `AKASHML_BASE_URL` (optional): Base URL for inference (default: https://api.akashml.com/v1).
- `DEFAULT_MODEL` (optional): Fallback model if depth not specified.

Models are selected by depth:
- `quick`: Qwen/Qwen3-30B-A3B
- `standard`: meta-llama/Llama-3.3-70B-Instruct
- `deep`: deepseek-ai/DeepSeek-V3.2

Notes:
- Do not commit API keys into `deploy.yaml` or git history.
- Akash Console allows setting env vars at deploy time.

---

## How Audits Work

1. **Diff parsing** extracts files, additions, deletions, and language hints.
2. **Audit passes** send the diff to specialized prompts:
   - Security
   - Quality
   - Performance
   - Best practices
3. **Scoring** uses weighted averages for an overall score.
4. **Synthesis** combines findings into a verdict and summary.

---

## UI Overview

The UI is intentionally minimal for demo speed:
- Diff input textarea with a working sample.
- Audit type selectors (checkboxes).
- Depth selector (quick/standard/deep).
- Results with score cards, summary, and per-audit tabs.

Frontend lives in:
- `templates/index.html`
- `static/app.js`

---

## Deployment on Akash

1. Build and push a public image:
   ```bash
   docker build -t YOUR_DOCKERHUB_USERNAME/change-aware-auditor:latest .
   docker push YOUR_DOCKERHUB_USERNAME/change-aware-auditor:latest
   ```
2. Update `deploy.yaml` with your image.
3. Deploy in Akash Console.
4. Set `AKASHML_API_KEY` as an environment variable in the deployment.

Important:
- Use Akash Console secrets or env vars for keys.
- Avoid storing any real secrets in `deploy.yaml`.
- The SDL template leaves key values blank; you must fill them before deploying.

---

## Limitations and Known Issues

- Model responses may return non-JSON. The parser falls back to raw content.
- Large diffs are chunked per file; very large single-file diffs may still be heavy.
- Cache is in-memory only (per instance).
- Rate limiting is in-memory only (per instance).
- Minimal tests only; no CI pipeline yet.

---

## Roadmap Ideas

Short-term:
- Persist rate limits with Redis or a gateway.
- Refine error messaging for model failures and partial parses.
- Expand tests (API responses, UI).

Medium-term:
- Improve chunking (size-based) and merge results more intelligently.
- Persist cache across instances.
- Add file-level heatmaps for demo impact.

Future:
- Apply patch suggestions automatically with a one-click diff.
- Run generated tests against the patched code.
- GitHub/GitLab integration for PR comments.

---

## Hackathon Context

Built for "AI Agent Build Night with AkashML" (January 2026).
- Focus: 1-day hackathon building an AI agent using Akash Console + AkashML.
- Goal: A useful, demonstrable agent with real deployment flow.
- **Status: DEMO EXPIRED** - The hackathon API credits have run out. You must
  provide your own `AKASHML_API_KEY` to use this project.

---

## Contributing

This is a hackathon project. Contributions are welcome:
- Keep prompts concise and structured.
- Favor deterministic, parseable JSON output.
- Avoid adding nonessential dependencies before the demo.

---

## Credits

Powered by AkashML for inference and Akash Network for deployment.
