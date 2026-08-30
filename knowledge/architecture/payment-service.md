# Payment Service Architecture

Payment Service is responsible for payment authorization.

Components:

- API Gateway
- Payment Service
- PostgreSQL
- Redis
- External Payment Gateway

Request flow:

API Gateway
→ Payment Service
→ PostgreSQL
→ External Payment Gateway

Important metrics:

- request latency
- HTTP 5xx rate
- payment timeout rate
- database latency