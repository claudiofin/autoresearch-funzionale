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

CRITICAL RULE: You are a pure Software Architect. You must reason in terms of ARCHITECTURAL PATTERNS and PARADIGMS, never specific technologies.

VIOLATION RULES (STRICT):
- NEVER mention specific technologies (e.g., "Node.js", "Python", "PostgreSQL", "MongoDB", "AWS", "Convex", "Supabase", "Firebase", "Express", "FastAPI", "GraphQL", "REST", "WebSocket", "gRPC").
- Instead of technology names, use paradigm descriptions:
  - Instead of "REST API" → "Request-Response API with resource-oriented operations"
  - Instead of "GraphQL" → "Declarative query API with client-specified responses"
  - Instead of "WebSockets" → "Bidirectional real-time communication channel"
  - Instead of "PostgreSQL" → "Relational database with ACID transactions"
  - Instead of "MongoDB" → "Document-oriented database with flexible schemas"
  - Instead of "Redis" → "In-memory key-value store for caching"
  - Instead of "RabbitMQ" → "Message broker for asynchronous job processing"

## State Machine (spec_machine.json)
```json
{json.dumps(machine, indent=2)}
```

## Project Context
{context_text[:5000]}

## Rules for Functional Backend Analysis

### 1. API PARADIGM SELECTION
Analyze the state machine and context to determine the most appropriate API paradigm:
- Request-Response (synchronous request/response pattern for standard CRUD operations)
- Declarative Query (client specifies exactly what data it needs, server resolves complex queries)
- RPC-style (direct invocation of server-side operations/actions)
- Real-time Bidirectional (persistent connection for server-to-client push notifications)
- Event-Driven (publish/subscribe pattern for decoupled async communication)

Justify the choice based on:
- Frequency of data updates (real-time vs on-demand)
- Complexity of data relationships (simple fetch vs complex joins)
- Client flexibility needs (fixed response vs custom queries)
- Server push requirements (notifications, live updates)

### 2. DATA MODEL PARADIGM
Determine the appropriate data storage paradigm based on the domain:
- Relational (structured data with strict schemas, ACID transactions, complex joins)
- Document-oriented (flexible schemas, hierarchical data, fast reads)
- Key-Value (simple lookups, caching, session storage)
- Time-Series (historical data, analytics, trend analysis)
- Graph (complex relationships, network analysis, recommendations)

Justify based on:
- Data structure complexity
- Transaction requirements (ACID vs eventual consistency)
- Query patterns (point lookups vs complex aggregations)
- Scalability needs (vertical vs horizontal)

### 3. OPERATIONAL CONTRACTS
For each state transition that requires backend interaction, define:
- Operation name and purpose
- Input parameters (types, constraints, validation rules)
- Output structure (data shape, success/error states)
- Side effects (what changes in the system)
- Idempotency requirements (can it be safely retried?)

### 4. ASYNCHRONOUS PROCESSING PATTERNS
Identify operations that cannot be synchronous:
- Long-running computations (clustering, batch processing)
- External service calls (email, payment, third-party APIs)
- Heavy data processing (aggregations, report generation)

For each, specify:
- Pattern: Job Queue, Pub/Sub, Webhook, or Polling
- Timeout expectations
- Fallback behavior on failure
- Progress tracking mechanism

### 5. SECURITY ARCHITECTURE
Define the security model:
- Authentication strategy (stateless tokens vs stateful sessions)
- Authorization model (RBAC, ABAC, or simple role-based)
- Data isolation (multi-tenancy, row-level security)
- Rate limiting strategy (per-user, per-endpoint, global)
- Audit logging requirements

### 6. ERROR HANDLING CONTRACTS
Map system states to error handling strategies:
- Transient errors (network timeout, temporary unavailability) → retry with backoff
- Permanent errors (not found, forbidden) → immediate failure with user guidance
- Data validation errors → structured error response with field-level details
- System errors (500) → generic error with request ID for debugging

### 7. CACHING STRATEGY
Define caching requirements:
- Which data benefits from caching (frequently read, rarely changed)
- Cache invalidation strategy (time-based, event-based, manual)
- Cache scope (client-side, edge/CDN, server-side, database query cache)
- Consistency requirements (strong vs eventual)

## Output Format

Respond ONLY with valid Markdown (no code blocks, no extra text):

# Backend Functional Specification

## 1. API Architecture

### 1.1 Paradigm Selection
[Describe the recommended API paradigm and justify the choice]

### 1.2 Authentication Flow
| Operation | Input | Output | Auth Required | Idempotent | Description |
|-----------|-------|--------|---------------|------------|-------------|
| Login | credentials | session token | No | No | Validate credentials, establish session |
| Refresh | refresh token | new access token | Yes | Yes | Extend session validity |
| Logout | session token | confirmation | Yes | Yes | Terminate session |

### 1.3 Data Operations
| Operation | Input | Output | Cache Strategy | Description |
|-----------|-------|--------|----------------|-------------|
| Fetch Dashboard | user_id | dashboard data | 5min TTL | Aggregate clinic profile, savings, recent activity |
| Search Catalog | filters | paginated results | 10min TTL | Search and filter available items |
| ...

### 1.4 Command Operations
| Operation | Input | Output | Idempotent | Description |
|-----------|-------|--------|------------|-------------|
| Join Group | group_id, quantity | confirmation | Yes | Request participation in purchase group |
| Calculate Benchmark | parameters | job_id | Yes | Trigger async clustering calculation |
| ...

## 2. Data Model

### 2.1 Paradigm Selection
[Describe recommended data storage paradigm and justify]

### 2.2 Entity Definitions
- **EntityName**: field (type, constraints), field (type, constraints), ...
- ...

### 2.3 Relationships
- EntityA 1:N EntityB (description of relationship)
- EntityC N:N EntityD (via junction table)
- ...

## 3. Asynchronous Processing

| Operation | Pattern | Timeout | Fallback | Progress Tracking |
|-----------|---------|---------|----------|-------------------|
| Clustering Calculation | Job Queue + Polling | 30s | Cached benchmark data | Poll job status endpoint |
| ...

## 4. Security Architecture

### 4.1 Authentication
[Describe auth strategy: stateless vs stateful, token lifecycle, etc.]

### 4.2 Authorization
[Describe authz model: roles, permissions, data isolation]

### 4.3 Rate Limiting
| Operation Type | Limit | Window | Action on Exceed |
|----------------|-------|--------|------------------|
| Authentication | 5 attempts | 15min | Temporary lockout |
| Data Queries | 60 requests | 1min | Throttle response |

## 5. Error Handling

| Error Type | Client Action | Retry Strategy | User Guidance |
|------------|---------------|----------------|---------------|
| Session Expired | Clear session, re-authenticate | No retry | Redirect to login |
| Not Found | Show empty state | No retry | Offer refresh/search |
| Server Error | Show error banner | Exponential backoff (3x) | "Please try again" |
| Rate Limited | Show warning | Wait for window reset | "Too many requests" |

## 6. Caching Strategy

| Data Type | Cache Level | TTL | Invalidation | Consistency |
|-----------|-------------|-----|--------------|-------------|
| Dashboard | Server + Client | 5min | Time-based | Eventual |
| Catalog | Edge + Server | 10min | Time-based | Eventual |
| Benchmark | Server | 15min | Event-based (on recalc) | Strong |
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