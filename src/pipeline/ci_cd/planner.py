"""
CI/CD Planner - generates functional CI/CD specification.

Derives:
- Integration test matrix from edge cases
- Environment strategy (Dev/Staging/Prod)
- Deployment strategy (Blue-Green / Rolling)
- Observability rules (monitoring, auto-rollback)
- Secret management strategy
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from llm.client import call_llm


def generate_ci_cd_spec(spec_file: str, backend_spec_file: str, output_file: str) -> dict:
    """Generate CI/CD functional specification from specs."""
    
    # Load files
    with open(spec_file, "r") as f:
        spec = f.read()
    
    with open(backend_spec_file, "r") as f:
        backend_spec = f.read()
    
    # Build the prompt
    prompt = f"""Analyze the frontend and backend specifications to generate a CI/CD FUNCTIONAL SPECIFICATION.

## Frontend Specification (spec.md)
{spec[:4000]}

## Backend Specification (backend_spec.md)
{backend_spec[:4000]}

## Rules for CI/CD Analysis

### 1. STATE-BASED INTEGRATION TESTING
Every edge case in the spec must be translated into an automated integration test:
- EC001: Network drops during group join → Mock 503 on POST /groups/join
- EC002: Session expires while browsing → Mock 401 on any GET
- EC003: Clustering timeout → Mock 30s delay on /benchmark/calculate
- EC004: Cancel during partial load → Cancel request mid-flight
- EC005: Zero search results → Return empty array from /catalog
- EC006: Double-tap JOIN_GROUP → Send 2 identical POST within 100ms

### 2. ENVIRONMENT PARITY
Define three environments with clear purposes:
- Dev: Development, auto-migrate on deploy, direct deployment
- Staging: Pre-production, auto-migrate before deploy, Blue-Green
- Production: Live, auto-migrate before deploy, Rolling Updates

### 3. ZERO DOWNTIME DEPLOYMENT
- Blue-Green for Staging: switch traffic only after health check passes
- Rolling Updates for Production: update pods one at a time
- Database migrations must run BEFORE app deployment
- Feature flags for gradual rollout

### 4. OBSERVABILITY MAPPING
Configure monitoring for state transitions:
- Track rate of transitions to `error` state
- If error rate > 5% in 5 minutes → Auto-rollback
- Track API latency (loading → success > 3s = alert)
- Track auth failure rate (> 10% = security alert)
- Sentry for frontend error tracking
- Structured logging for backend

### 5. SECRET INJECTION
- Never store secrets in code
- Use Vault or environment variables
- Inject via CI/CD pipeline at deploy time
- Rotate secrets on a schedule (90 days)
- Separate secrets per environment

### 6. CI PIPELINE STAGES
Define the stages of the CI pipeline:
1. Lint & Type Check
2. Unit Tests
3. Integration Tests (state-based)
4. Security Scan
5. Build & Push
6. Deploy to Staging
7. E2E Tests
8. Deploy to Production

## Output Format

Respond ONLY with valid Markdown (no code blocks, no extra text):

# CI/CD Functional Specification

## 1. Integration Test Matrix

| Edge Case | Test Type | Simulation | Expected Behavior | Priority |
|-----------|-----------|------------|-------------------|----------|
| EC001: Network drops during group join | API failure | Mock 503 on POST /groups/join | Error state, retry option preserved | high |
| EC002: Session expires while browsing | Auth failure | Mock 401 on any GET | Redirect to session_expired | high |
| EC003: Clustering timeout | Async timeout | Mock 30s delay on /benchmark/calculate | Error state, cached fallback | medium |
| EC004: Cancel during partial load | Request cancellation | Abort mid-flight request | Return to previous state | medium |
| EC005: Zero search results | Empty response | Return empty array from /catalog | Empty state with illustration | low |
| EC006: Double-tap JOIN_GROUP | Idempotency | 2 identical POST within 100ms | Only 1 processed | high |

## 2. Environment Strategy

| Environment | Purpose | DB Migration | Deploy Strategy | Auto-Rollback |
|-------------|---------|--------------|-----------------|---------------|
| Dev | Development | Auto on deploy | Direct | No |
| Staging | Pre-production | Auto before deploy | Blue-Green | Yes (on health check fail) |
| Production | Live | Auto before deploy | Rolling Update | Yes (on error rate > 5%) |

## 3. Deployment Strategy

### 3.1 Blue-Green Deployment (Staging)
1. Deploy new version to "green" environment
2. Run health checks (all endpoints respond 200)
3. Run smoke tests (critical user flows)
4. Switch traffic from "blue" to "green"
5. Keep "blue" for 1 hour (quick rollback)

### 3.2 Rolling Update (Production)
1. Deploy new version to 1 pod at a time
2. Wait for health check before next pod
3. Monitor error rate during rollout
4. If error rate > 5%, pause and alert
5. If error rate > 10%, auto-rollback

### 3.3 Database Migration Strategy
1. Run backward-compatible migrations first (add columns, not remove)
2. Deploy application code
3. Run data migration (backfill, transform)
4. Run cleanup migration (remove old columns) in next release

## 4. Observability Rules

### 4.1 Metrics
| Metric | Threshold | Window | Action |
|--------|-----------|--------|--------|
| Error rate (state → error) | > 5% | 5min | Auto-rollback |
| API latency (loading → success) | > 3s | 1min | Alert team |
| Auth failure rate | > 10% | 5min | Alert security |
| DB connection pool | > 80% | 1min | Scale up |

### 4.2 Logging
- Structured JSON logging on backend
- Correlation ID per request (trace from frontend to backend)
- Log level: INFO for normal, WARN for retry, ERROR for failure
- PII must be masked in logs

### 4.3 Alerting
| Alert | Channel | Response Time |
|-------|---------|---------------|
| Auto-rollback triggered | PagerDuty | 5min |
| Error rate spike | Slack #alerts | 15min |
| Auth failure spike | Slack #security | 15min |
| Latency degradation | Slack #perf | 30min |

## 5. CI Pipeline

### 5.1 Stages
| Stage | Timeout | Failure Action |
|-------|---------|----------------|
| Lint & Type Check | 5min | Block merge |
| Unit Tests | 10min | Block merge |
| Integration Tests | 15min | Block merge |
| Security Scan | 5min | Block merge (critical vulns) |
| Build & Push | 5min | Retry once |
| Deploy Staging | 10min | Alert |
| E2E Tests | 15min | Block production |
| Deploy Production | 15min | Alert + monitor |

### 5.2 Test Coverage Requirements
- Unit tests: > 80% coverage
- Integration tests: 100% of edge cases covered
- E2E tests: Critical user flows (login, browse, join group)

## 6. Secret Management

| Secret | Source | Injection | Rotation |
|--------|--------|-----------|----------|
| LLM_API_KEY | Vault | Env var at deploy | 90 days |
| DB_PASSWORD | Vault | Env var at deploy | 90 days |
| JWT_SECRET | Vault | Env var at deploy | 90 days |
| EXTERNAL_API_KEY | Config | Env var at deploy | On compromise |

### 6.1 Security Rules
- No secrets in code or config files
- No secrets in CI/CD logs (mask in output)
- Separate secrets per environment
- Audit access to secrets

## 7. Rollback Strategy

| Trigger | Action | Downtime |
|---------|--------|----------|
| Error rate > 5% | Auto-rollback to previous version | < 1min |
| Health check fail | Block deployment | 0min |
| Security vulnerability | Emergency patch + deploy | < 30min |
| Data corruption | Restore from backup | < 1hr |
"""
    
    print(f"  🤖 Calling LLM for CI/CD spec generation...")
    print(f"     Frontend spec: {len(spec)} chars")
    print(f"     Backend spec: {len(backend_spec)} chars")
    
    response = call_llm(prompt, system_message="You are a Senior DevOps Architect. Generate ONLY valid Markdown. No code blocks, no extra text. Start with '# CI/CD Functional Specification'.")
    
    # Write output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        f.write(response)
    
    print(f"  ✅ CI/CD spec written to {output_file}")
    
    return {
        "success": True,
        "output": output_file,
        "size_chars": len(response)
    }