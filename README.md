# Implement REST APIs Assessment

## Overview
This project implements a Python tool gateway that connects registered tools to a REST API client. It supports looking up an order and updating an order's status. The gateway validates requests, checks caller permissions, invokes registered handlers, validates provider responses, and returns structured results.

## Objectives
- Integrate registered tool handlers with REST API operations.
- Validate inputs and provider outputs using Pydantic schemas.
- Enforce role-based access control before HTTP requests.
- Convert timeouts, missing resources, and provider failures into structured statuses.
- Prevent duplicate write operations through idempotency.
- Apply bounded retries to read requests and rolling-window rate limiting.
- Record metrics and emit structured events with sensitive-field redaction.

## Architecture
- `src/contracts.py`: tool-call/result contracts and status values.
- `src/schemas.py`: input and output models.
- `src/registry.py`: versioned tool registry and specifications.
- `src/tool_setup.py`: handlers for `order_lookup` and `order_update`.
- `src/rest_client.py`: REST client for order operations.
- `src/fake_rest_server.py`: local fake REST server for repeatable tests.
- `src/gateway.py`: gateway execution pipeline and `dispatch()` entry point.
- `src/gateway_setup.py`: local test-environment setup.
- `src/reliability.py`: idempotency and reliability helpers.
- `src/observability.py`: metrics and structured event logging.
- `tests/`: automated REST integration, security, and reliability tests.

## Supported tools
### `order_lookup`
Reads an order by its identifier. Authorized roles: `viewer`, `operator`, and `admin`.

### `order_update`
Updates an order's status. Authorized roles: `operator` and `admin`. Successful write results are cached so replaying the same request does not repeat the REST update.

## Reliability and security
The gateway rejects invalid inputs before provider calls, checks tool/version registration and caller roles, limits requests per principal over a rolling time window, and applies bounded retries to reads. It does not automatically retry writes. Provider failures are mapped to structured statuses without exposing raw exception details in public results. Event logging filters sensitive fields, while metrics track total requests, outcomes, retries, provider attempts, idempotency cache hits, and latency.

## Setup and execution
Run commands from the project root in the configured Python environment. Install project dependencies from `requirements.txt` if it exists, then execute:

```cmd
python -m pytest -q
```

Observed local verification for this assessment: **41 passed**.

## Reflection (approximately 300 words)
Building this REST API gateway helped me understand that tool integration requires more than sending an HTTP request and returning the response. A reliable gateway needs clear contracts, input validation, access control, consistent error handling, and observability around every execution.

One important learning was to validate arguments before making an external request. This prevents malformed input from reaching the provider and avoids unnecessary side effects. Role-based authorization is equally important: a caller should only be able to invoke tools allowed for their role, and denied or unknown operations should not trigger HTTP requests.

I also learned why write operations need different reliability rules from read operations. Retrying a read after a transient timeout is often reasonable, but blindly retrying a write can repeat a side effect. Idempotency storage allows a successful write result to be reused for an identical request, while detecting reuse of the same key for a different request. The tests made these distinctions concrete.

The assessment also strengthened my understanding of structured error mapping. Timeouts, missing orders, provider failures, invalid inputs, and authorization failures should be distinguishable through stable status values. At the same time, public results and logs should not expose raw provider details, tracebacks, or sensitive request fields.

Finally, metrics and event logs make behavior easier to verify. Counters for total requests, retries, provider attempts, outcomes, and idempotency cache hits provide evidence that reliability mechanisms are working rather than merely being present in code.

The complete test run passed 41 tests, covering REST API integration, security behavior, and gateway reliability. This project gave me practical experience connecting registered tools to a REST client while keeping validation, authorization, retries, idempotency, rate limiting, and observability within a single execution workflow.
