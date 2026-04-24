"""
Backend Architect - generates functional backend specification from state machine.

Derives:
- API endpoints from loading states
- Auth contracts from authenticating/session_expired states
- Data schema from project context
- Async patterns from calculation states
- Idempotency requirements from command events
"""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from llm.client import call_llm_text


def generate_backend_spec(machine_file: str, context_file: str, output_file: str) -> dict:
    """Generate backend functional specification from state machine and context."""
    
    # Load state machine
    with open(machine_file, "r") as f:
        machine = json.load(f)
    
    # Load context
    with open(context_file, "r") as f:
        context_text = f.read()
    
    # Build the prompt
    prompt = f"""Analyze this state machine and project context to generate a BACKEND FUNCTIONAL SPECIFICATION.

## State Machine (spec_machine.json)
```json
{json.dumps(machine, indent=2)}
```

## Project Context
{context_text[:5000]}

## Rules for Backend Analysis

### 1. STATE-TO-ENDPOINT MAPPING
Every `loading` state in the machine corresponds to a data-fetching API call.
Map each loading transition to an endpoint:
- loading → success.dashboard → GET /api/dashboard
- loading → success.catalog → GET /api/catalog
- loading → success.offers → GET /api/offers/active
- loading → success.benchmark → GET /api/benchmark/cluster
- loading → success.groups → GET /api/groups/active

### 2. AUTH STATE COHERENCE
- `authenticating` state → POST /api/auth/login (credentials validation)
- `session_expired` state → POST /api/auth/refresh (token refresh)
- Define JWT/OAuth2 token lifecycle: access_token (15min), refresh_token (7d)

### 3. TRANSITION COMMANDS
Events that are NOT navigation (NAVIGATE_*) are backend commands:
- JOIN_GROUP → POST /api/groups/join (idempotent check required)
- CALCULATE_CLUSTER → POST /api/benchmark/calculate (async operation)
- REFRESH_DATA → GET with cache-busting or ETag

### 4. ASYNC CALCULATION PATTERN
If a state involves computation (e.g., clustering_calculation):
- Backend must use Job Queue pattern
- Client polls GET /api/jobs/{id}/status
- Timeout: 30s, then fallback to cached data

### 5. DATA SCHEMA DERIVATION
Extract entities from project_context.md:
- If context mentions "clinics", "purchases", "medicines" → define tables
- Define relationships (1:N, N:N) based on how data is fetched together
- Define validation rules from the spec's Data Validation section

### 6. ERROR CONTRACTS
Map HTTP status codes to state machine states:
- 401 → session_expired
- 403 → error (forbidden)
- 404 → empty (not found)
- 500 → error (retry with backoff)
- 503 → error (network unavailable)

### 7. IDEMPOTENCY
For POST/PATCH/DELETE operations:
- Define idempotency key strategy (X-Idempotency-Key header)
- Specify which operations MUST be idempotent (double-tap prevention)

## Output Format

Respond ONLY with valid Markdown (no code blocks, no extra text):

# Backend Functional Specification

## 1. API Endpoints

### 1.1 Authentication
| Endpoint | Method | Auth Required | Idempotent | Description |
|----------|--------|---------------|------------|-------------|
| POST /api/auth/login | POST | No | No | Validate credentials, return JWT pair |
| POST /api/auth/refresh | POST | Yes (refresh token) | Yes | Exchange refresh token for new access token |
| POST /api/auth/logout | POST | Yes (access token) | Yes | Invalidate refresh token |

### 1.2 Data Fetching (GET)
| Endpoint | Method | Auth Required | Cache | Description |
|----------|--------|---------------|-------|-------------|
| GET /api/dashboard | GET | Yes | 5min | Fetch clinic profile, YTD savings, recent purchases |
| GET /api/catalog | GET | Yes | 10min | Search medicines with filters |
| ...

### 1.3 Commands (POST/PATCH/DELETE)
| Endpoint | Method | Auth Required | Idempotent | Description |
|----------|--------|---------------|------------|-------------|
| POST /api/groups/join | POST | Yes | Yes | Request to join purchase group |
| ...

## 2. Async Operations
| Operation | Pattern | Timeout | Fallback | Polling Interval |
|-----------|---------|---------|----------|------------------|
| Clustering Calculation | Job Queue + Polling | 30s | Cached data | 2s |

## 3. Data Schema

### 3.1 Entities
- **Clinic**: id (UUID), name, role, active (boolean), created_at
- **Purchase**: id (UUID), clinic_id (FK), item, quantity, unit_price, date
- ...

### 3.2 Relationships
- Clinic 1:N Purchase
- Clinic N:N Group (via GroupMembership)
- ...

## 4. Error Contracts
| HTTP Status | State | Retryable | User Action |
|-------------|-------|-----------|-------------|
| 401 | session_expired | No | Re-authenticate |
| 403 | error | No | Show forbidden |
| 404 | empty | No | Show empty state |
| 500 | error | Yes | Retry with exponential backoff |
| 503 | error | Yes | Check connection, retry |

## 5. Idempotency Requirements
| Endpoint | Idempotency Key | Strategy |
|----------|-----------------|----------|
| POST /api/groups/join | X-Idempotency-Key | DB unique constraint on (clinic_id, group_id, key) |
| POST /api/auth/refresh | Token pair | Single-use refresh tokens |

## 6. Rate Limiting
| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /api/auth/login | 5 | 15min |
| GET /api/catalog | 60 | 1min |
| POST /api/benchmark/calculate | 3 | 10min |

## 7. Security Requirements
- All GET endpoints require valid access_token in Authorization header
- POST/PATCH/DELETE require access_token + idempotency key
- Refresh tokens stored in httpOnly cookie
- Rate limiting on auth endpoints to prevent brute force
"""
    
    print(f"  🤖 Calling LLM for backend spec generation...")
    print(f"     Machine: {len(machine.get('states', {}))} states")
    print(f"     Context: {len(context_text)} chars")
    
    response = call_llm_text(
        prompt,
        system_message="You are a Senior Backend Architect. Generate ONLY valid Markdown. No code blocks, no extra text. Start with '# Backend Functional Specification'.",
        max_tokens=8192
    )
    
    # Write output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        f.write(response)
    
    print(f"  ✅ Backend spec written to {output_file}")
    
    return {
        "success": True,
        "output": output_file,
        "size_chars": len(response)
    }