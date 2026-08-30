# Payment Service Runbook

## Symptoms

Common symptoms include:

- HTTP 500 errors
- PaymentTimeoutException
- Increased response latency
- Failed authorization requests

## Initial Investigation

1. Check application logs.
2. Check recent deployments.
3. Check database latency.
4. Check external payment gateway health.

## Deployment Related Issues

If the issue started immediately after a deployment:

1. Compare the current release with the previous release.
2. Review recent commits.
3. Check timeout configuration.
4. Consider rollback if the regression is confirmed.

## Rollback

Production rollback requires human approval.