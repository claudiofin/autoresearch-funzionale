"""
Security Auditor - generates security audit and threat model from specifications.

Analyzes frontend, backend, and CI/CD specs to produce:
- Security threat model with attack vectors and mitigations
- Security requirements (authentication, authorization, data protection)
- Compliance checklist (GDPR, HIPAA, SOC2 if relevant)
- Security architecture recommendations
- @SECURITY_RULES.md for LLM Wiki
"""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from llm.client import call_llm_text


def generate_security_spec(
    frontend_spec: str,
    backend_spec: str,
    ci_cd_spec: str,
    context: str,
    output_file: str,
) -> dict:
    """Generate security specification from all project specifications."""

    prompt = f"""Analyze the frontend, backend, and CI/CD specifications to generate a COMPREHENSIVE SECURITY AUDIT AND THREAT MODEL.

CRITICAL RULE: You are a pure Security Architect. You must reason in terms of SECURITY PATTERNS and THREAT MITIGATIONS, never specific tools or vendors.

VIOLATION RULES (STRICT):
- NEVER mention specific security tools (e.g., "OWASP ZAP", "Burp Suite", "Snyk", "SonarQube", "Auth0", "Okta", "AWS WAF", "Cloudflare").
- Instead of tool names, use paradigm descriptions:
  - Instead of "OAuth2" → "Delegated authorization framework"
  - Instead of "JWT" → "Stateless token-based authentication"
  - Instead of "AES-256" → "Strong symmetric encryption"
  - Instead of "TLS 1.3" → "Transport layer encryption"
  - Instead of "bcrypt" → "Adaptive password hashing"
  - Instead of "CSP headers" → "Content security policy directives"
  - Instead of "CORS" → "Cross-origin resource sharing policy"

## Frontend Specification
{frontend_spec[:3000]}

## Backend Specification
{backend_spec[:3000]}

## CI/CD Specification
{ci_cd_spec[:2000]}

## Project Context
{context[:2000]}

## Rules for Security Analysis

### 1. THREAT MODELING (STRIDE Framework)
For each component (frontend, backend, data storage, communication channel), analyze:
- **Spoofing:** Can an attacker impersonate a legitimate user or service?
- **Tampering:** Can data be modified in transit or at rest?
- **Repudiation:** Can actions be denied without audit trail?
- **Information Disclosure:** Can sensitive data be accessed by unauthorized parties?
- **Denial of Service:** Can the system be made unavailable?
- **Elevation of Privilege:** Can a user gain higher access than intended?

For each threat, specify:
- Likelihood (Low/Medium/High)
- Impact (Low/Medium/High/Critical)
- Mitigation strategy

### 2. AUTHENTICATION ARCHITECTURE
Analyze and recommend:
- Authentication flow (login, session management, logout)
- Token lifecycle (issuance, validation, refresh, revocation)
- Multi-factor authentication requirements
- Session security (timeout, concurrent sessions, secure storage)
- Password policy (complexity, rotation, hashing)

### 3. AUTHORIZATION MODEL
Analyze and recommend:
- Access control model (RBAC, ABAC, or simple role-based)
- Permission granularity (resource-level, action-level, field-level)
- Data isolation (multi-tenancy, row-level security)
- Privilege escalation prevention
- Admin/super-user controls

### 4. DATA PROTECTION
Analyze and recommend:
- Encryption at rest (what data, what strength, key management)
- Encryption in transit (protocol, certificate management)
- Data classification (public, internal, confidential, restricted)
- PII handling (collection, storage, processing, deletion)
- Data retention and disposal policies
- Backup encryption and security

### 5. API SECURITY
Analyze and recommend:
- Input validation strategy (server-side, client-side, both)
- Output encoding (XSS prevention, HTML escaping)
- Rate limiting and throttling (per-user, per-endpoint, global)
- CORS policy (allowed origins, methods, headers)
- Content Security Policy (inline scripts, external resources)
- API versioning and deprecation security

### 6. INFRASTRUCTURE SECURITY
Analyze and recommend:
- Network isolation (public vs private services)
- Secret management (storage, injection, rotation, audit)
- Least privilege principle (service accounts, API keys)
- Container/image security (if applicable)
- Dependency management (vulnerability scanning, updates)

### 7. COMPLIANCE REQUIREMENTS
Based on the project domain, identify relevant compliance frameworks:
- GDPR (if handling EU user data)
- HIPAA (if handling healthcare data)
- SOC2 (if serving enterprise clients)
- PCI-DSS (if handling payment data)
- Industry-specific regulations

For each applicable framework, list key requirements.

### 8. SECURITY MONITORING AND INCIDENT RESPONSE
Analyze and recommend:
- Security event logging (what to log, retention period)
- Intrusion detection (anomaly detection, pattern matching)
- Incident response plan (detection, containment, eradication, recovery)
- Security audit schedule (penetration testing, code review, config review)

## Output Format

Respond ONLY with valid Markdown (no code blocks, no extra text):

# Security Audit and Threat Model

## 1. Executive Summary
[Brief overview of the security posture, key findings, and critical recommendations]

## 2. Threat Model (STRIDE Analysis)

### 2.1 Threat Matrix
| Threat ID | Component | STRIDE Category | Description | Likelihood | Impact | Risk Level | Mitigation |
|-----------|-----------|-----------------|-------------|------------|--------|------------|------------|
| T001 | [Component] | [Category] | [Description] | High/Medium/Low | High/Medium/Low/Critical | Critical/High/Medium/Low | [Mitigation strategy] |
| ...

### 2.2 Trust Boundaries
[Describe the trust boundaries in the system and how they are protected]

### 2.3 Attack Surface Analysis
[Describe the main attack vectors and how they are mitigated]

## 3. Authentication Architecture

### 3.1 Authentication Flow
[Describe the recommended authentication flow]

### 3.2 Session Management
| Aspect | Recommendation | Rationale |
|--------|---------------|-----------|
| Token type | [Recommendation] | [Why] |
| Token lifetime | [Recommendation] | [Why] |
| Refresh strategy | [Recommendation] | [Why] |
| Session storage | [Recommendation] | [Why] |
| Concurrent sessions | [Recommendation] | [Why] |

### 3.3 Password Policy
| Requirement | Recommendation |
|-------------|---------------|
| Minimum length | [Recommendation] |
| Complexity | [Recommendation] |
| Hashing algorithm | [Recommendation] |
| Rotation period | [Recommendation] |

## 4. Authorization Model

### 4.1 Access Control
[Describe the recommended access control model]

### 4.2 Role Definitions
| Role | Permissions | Data Access |
|------|-------------|-------------|
| [Role name] | [Permissions] | [Data scope] |
| ...

### 4.3 Data Isolation
[Describe multi-tenancy and data isolation strategy]

## 5. Data Protection

### 5.1 Encryption Strategy
| Data Type | At Rest | In Transit | Key Management |
|-----------|---------|------------|----------------|
| [Data type] | [Algorithm/Approach] | [Protocol] | [Strategy] |
| ...

### 5.2 Data Classification
| Classification | Description | Handling Requirements |
|----------------|-------------|----------------------|
| Public | [Description] | [Requirements] |
| Internal | [Description] | [Requirements] |
| Confidential | [Description] | [Requirements] |
| Restricted | [Description] | [Requirements] |

### 5.3 PII Handling
[Describe PII collection, storage, processing, and deletion policies]

### 5.4 Data Retention
| Data Type | Retention Period | Deletion Method |
|-----------|-----------------|-----------------|
| [Data type] | [Period] | [Method] |
| ...

## 6. API Security

### 6.1 Input Validation
| Layer | Validation Type | Implementation |
|-------|----------------|----------------|
| Client | [Type] | [Approach] |
| Server | [Type] | [Approach] |
| Database | [Type] | [Approach] |

### 6.2 Rate Limiting
| Endpoint Type | Limit | Window | Action on Exceed |
|---------------|-------|--------|------------------|
| Authentication | [Limit] | [Window] | [Action] |
| Data queries | [Limit] | [Window] | [Action] |
| Write operations | [Limit] | [Window] | [Action] |

### 6.3 Cross-Origin Policy
[Describe CORS and Content Security Policy recommendations]

## 7. Infrastructure Security

### 7.1 Network Architecture
[Describe network isolation and segmentation recommendations]

### 7.2 Secret Management
| Secret Type | Storage | Injection | Rotation | Audit |
|-------------|---------|-----------|----------|-------|
| [Type] | [Approach] | [Method] | [Schedule] | [Method] |
| ...

### 7.3 Dependency Security
[Describe dependency management and vulnerability scanning strategy]

## 8. Compliance Checklist

### 8.1 Applicable Frameworks
[List applicable compliance frameworks based on project domain]

### 8.2 Compliance Requirements
| Framework | Requirement | Status | Implementation |
|-----------|-------------|--------|----------------|
| [Framework] | [Requirement] | Required/Optional | [How to implement] |
| ...

## 9. Security Monitoring and Incident Response

### 9.1 Security Logging
| Event Type | Log Level | Retention | Alert Trigger |
|------------|-----------|-----------|---------------|
| Authentication failure | WARN | 90 days | > 5 failures in 5min |
| Privilege escalation | ERROR | 1 year | Immediate |
| Data access (confidential) | INFO | 90 days | N/A |
| ...

### 9.2 Incident Response Plan
| Phase | Action | Responsible | Timeline |
|-------|--------|-------------|----------|
| Detection | [Action] | [Role] | [Time] |
| Containment | [Action] | [Role] | [Time] |
| Eradication | [Action] | [Role] | [Time] |
| Recovery | [Action] | [Role] | [Time] |
| Post-Incident | [Action] | [Role] | [Time] |

### 9.3 Security Audit Schedule
| Audit Type | Frequency | Scope |
|------------|-----------|-------|
| Penetration testing | [Frequency] | [Scope] |
| Code review | [Frequency] | [Scope] |
| Configuration review | [Frequency] | [Scope] |
| Dependency scan | [Frequency] | [Scope] |

## 10. Security Recommendations Summary

### 10.1 Critical (Must Implement)
1. [Critical recommendation]
2. ...

### 10.2 High Priority
1. [High priority recommendation]
2. ...

### 10.3 Medium Priority
1. [Medium priority recommendation]
2. ...

### 10.4 Low Priority
1. [Low priority recommendation]
2. ...
"""

    print(f"  🤖 Calling LLM for security audit generation...")
    print(f"     Frontend spec: {len(frontend_spec)} chars")
    print(f"     Backend spec: {len(backend_spec)} chars")
    print(f"     CI/CD spec: {len(ci_cd_spec)} chars")
    print(f"     Context: {len(context)} chars")

    response = call_llm_text(
        prompt,
        system_message="You are a Senior Security Architect. Generate ONLY valid Markdown. No code blocks, no extra text. Start with '# Security Audit and Threat Model'.",
        max_tokens=8192,
    )

    # Write output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        f.write(response)

    print(f"  ✅ Security spec written to {output_file}")

    return {
        "success": True,
        "output": output_file,
        "size_chars": len(response),
    }