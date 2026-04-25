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
from llm.client import call_llm_text


def generate_ci_cd_spec(spec_file: str, backend_spec_file: str, output_file: str) -> dict:
    """Generate CI/CD functional specification from specs."""
    
    # Load files
    with open(spec_file, "r") as f:
        spec = f.read()
    
    with open(backend_spec_file, "r") as f:
        backend_spec = f.read()
    
    # Build the prompt
    prompt = f"""Analyze the frontend and backend specifications to generate a CI/CD FUNCTIONAL SPECIFICATION.

CRITICAL RULE: You are a pure DevOps Architect. You must reason in terms of QUALITY GATES, RELEASE STRATEGIES, and OPERATIONAL PATTERNS, never specific platforms or tools.

VIOLATION RULES (STRICT):
- NEVER mention specific platforms or tools (e.g., "GitHub Actions", "Jenkins", "GitLab CI", "Vercel", "AWS", "Docker", "Kubernetes", "PagerDuty", "Slack", "Sentry", "Vault").
- Instead of platform names, use paradigm descriptions:
  - Instead of "GitHub Actions" → "CI/CD orchestration system"
  - Instead of "Vercel" → "Edge hosting platform with automatic previews"
  - Instead of "AWS" → "Cloud infrastructure provider"
  - Instead of "Docker" → "Container-based deployment"
  - Instead of "Kubernetes" → "Container orchestration platform"
  - Instead of "PagerDuty" → "On-call alerting system"
  - Instead of "Slack" → "Team communication channel"
  - Instead of "Sentry" → "Error tracking and crash reporting service"
  - Instead of "Vault" → "Secrets management system"

## Frontend Specification (spec.md)
{spec[:4000]}

## Backend Specification (backend_spec.md)
{backend_spec[:4000]}

## Rules for Functional CI/CD Analysis

### 1. STATE-BASED INTEGRATION TESTING
Every edge case in the frontend specification must be translated into an automated integration test scenario:
- Network failures during critical operations (connection drops, timeouts)
- Authentication failures (session expiration, token refresh failures)
- Async operation timeouts (long-running calculations, external service delays)
- Request cancellation (user navigates away during loading)
- Empty/edge case responses (no search results, zero data)
- Idempotency verification (duplicate requests, double-clicks)

For each scenario, define:
- What is being simulated
- Expected system behavior (state transitions, user feedback)
- Priority level (high/medium/low)

### 2. ENVIRONMENT STRATEGY
Define the environment lifecycle based on the project's risk profile and release cadence:
- Development/Ephemeral: Short-lived environments for feature validation
- Staging/Pre-production: Production-parity environment for final validation
- Production: Live environment serving real users

For each environment, specify:
- Purpose and entry criteria
- Data strategy (seed data, anonymized production data, fresh data)
- Deployment trigger (auto on merge, manual approval, scheduled)
- Cleanup policy (auto-destroy after PR merge, retain for N days)

### 3. RELEASE STRATEGY
Determine the appropriate deployment strategy based on:
- Downtime tolerance (zero-downtime required vs acceptable)
- Rollback speed requirements (instant vs gradual)
- Infrastructure complexity (simple vs distributed)
- User impact (internal tool vs customer-facing)

Available strategies:
- Direct Deployment: Deploy directly to production (simple, fast, higher risk)
- Blue-Green: Maintain two identical environments, switch traffic after validation
- Rolling Update: Gradually replace instances one at a time
- Canary: Deploy to a small subset of users first, gradually expand
- Feature Flags: Deploy code but gate features behind configuration toggles

Justify the choice based on the project's requirements.

### 4. QUALITY GATES (CI PIPELINE)
Define the mandatory checks that code must pass before promotion:
- Static Analysis: Linting, type checking, code style enforcement
- Unit Testing: Automated tests for individual components/functions
- Integration Testing: Tests for component interactions and API contracts
- Security Scanning: Vulnerability detection in code and dependencies
- Build Verification: Ensure the application builds successfully
- Performance Benchmarks: Verify performance thresholds are met

For each gate, specify:
- Timeout threshold
- Failure action (block promotion, warn, ignore)
- Retry policy

### 5. SECRET AND CONFIGURATION MANAGEMENT
Define the strategy for managing sensitive configuration:
- Storage: Where secrets are stored (never in code/repository)
- Injection: How secrets are made available at runtime
- Isolation: How secrets are separated per environment
- Rotation: How often secrets are rotated
- Audit: How secret access is logged and monitored

### 6. MONITORING AND OBSERVABILITY
Define the health monitoring strategy:
- Health Checks: What endpoints/statuses verify the application is running
- Business Metrics: What metrics indicate the application is functioning correctly
- Error Tracking: How errors are captured, aggregated, and alerted
- Performance Monitoring: How latency, throughput, and resource usage are tracked
- Log Aggregation: How logs are collected, structured, and searchable

Define thresholds and actions:
| Metric | Warning Threshold | Critical Threshold | Action |
|--------|-------------------|-------------------|--------|
| Error Rate | > 2% | > 5% | Alert / Auto-rollback |
| Latency (p95) | > 2s | > 5s | Alert team |
| ...

### 7. ROLLBACK STRATEGY
Define when and how to rollback deployments:
- Automatic triggers (error rate spike, health check failure, security vulnerability)
- Manual triggers (user reports, business metric degradation)
- Rollback procedure (how to revert to previous version)
- Post-rollback analysis (incident review, root cause analysis)

## Output Format

Respond ONLY with valid Markdown (no code blocks, no extra text):

# CI/CD Functional Specification

## 1. Integration Test Matrix

| Edge Case | Test Type | Simulation | Expected Behavior | Priority |
|-----------|-----------|------------|-------------------|----------|
| EC001: [Description] | [Type] | [What is simulated] | [Expected state transitions] | high/medium/low |
| ...

## 2. Environment Strategy

| Environment | Purpose | Entry Criteria | Data Strategy | Deployment Trigger | Cleanup |
|-------------|---------|----------------|---------------|-------------------|---------|
| Development | Feature validation | PR created | Fresh/seed data | Auto | Auto-destroy on merge |
| Staging | Pre-production validation | PR merged to main | Anonymized prod data | Auto on merge | Retain 7 days |
| Production | Live users | Manual approval | Production data | Manual | N/A |

## 3. Release Strategy

### 3.1 Strategy Selection
[Describe recommended deployment strategy and justify based on project requirements]

### 3.2 Deployment Procedure
1. [Step 1]
2. [Step 2]
3. ...

### 3.3 Feature Flag Strategy
[Describe how features should be gated and gradually released]

## 4. Quality Gates

| Gate | Purpose | Timeout | Failure Action | Retry Policy |
|------|---------|---------|----------------|--------------|
| Static Analysis | Code quality | 5min | Block | No retry |
| Unit Tests | Component correctness | 10min | Block | No retry |
| Integration Tests | API contracts | 15min | Block | 1 retry |
| Security Scan | Vulnerability detection | 5min | Block (critical) | No retry |
| Build Verification | Build integrity | 5min | Block | 1 retry |

### 4.1 Coverage Requirements
- Unit tests: > [X]% code coverage
- Integration tests: 100% of defined edge cases
- E2E tests: All critical user flows

## 5. Secret Management

| Secret Category | Storage | Injection | Isolation | Rotation |
|-----------------|---------|-----------|-----------|----------|
| Database credentials | Secrets manager | Environment variable | Per environment | 90 days |
| API keys | Secrets manager | Environment variable | Per environment | On compromise |
| ...

### 5.1 Security Rules
- Secrets never stored in code or configuration files
- Secrets injected at deployment time only
- Strict environment isolation (no cross-environment leakage)
- All secret access logged and audited
- Secrets masked in logs and CI/CD output

## 6. Monitoring and Observability

### 6.1 Health Checks
| Check Type | Endpoint/Method | Frequency | Timeout | Failure Action |
|------------|-----------------|-----------|---------|----------------|
| Liveness | [Health endpoint] | Every 10s | 5s | Restart instance |
| Readiness | [Ready endpoint] | Every 10s | 5s | Remove from traffic |

### 6.2 Business Metrics
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Error rate (state → error) | > 2% | > 5% | Alert / Auto-rollback |
| API latency (p95) | > 2s | > 5s | Alert team |
| Auth failure rate | > 5% | > 10% | Alert security |

### 6.3 Logging Strategy
- Structured logging format (JSON with correlation IDs)
- Log levels: INFO (normal), WARN (retry/degraded), ERROR (failure)
- PII and sensitive data must be masked
- Correlation ID propagated from client to backend

### 6.4 Alerting Channels
| Alert Type | Channel | Response Time |
|------------|---------|---------------|
| Auto-rollback triggered | On-call system | 5min |
| Error rate spike | Team channel | 15min |
| Security alert | Security team | 15min |

## 7. Rollback Strategy

| Trigger | Action | Downtime Expected |
|---------|--------|-------------------|
| Error rate > 5% | Auto-rollback to previous version | < 1min |
| Health check failure | Block deployment, alert | 0min |
| Security vulnerability | Emergency patch pipeline | < 30min |
| Data corruption | Restore from backup | < 1hr |
| Feature flag misconfiguration | Toggle flag off | < 30s |

### 7.1 Rollback Procedure
1. [Step 1: Detect and confirm rollback trigger]
2. [Step 2: Execute rollback]
3. [Step 3: Verify previous version is healthy]
4. [Step 4: Notify team]
5. [Step 5: Schedule post-incident review]
"""
    
    print(f"  🤖 Calling LLM for CI/CD spec generation...")
    print(f"     Frontend spec: {len(spec)} chars")
    print(f"     Backend spec: {len(backend_spec)} chars")
    
    response = call_llm_text(prompt, system_message="You are a Senior DevOps Architect. Generate ONLY valid Markdown. No code blocks, no extra text. Start with '# CI/CD Functional Specification'.")
    
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