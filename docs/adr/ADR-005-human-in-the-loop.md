# ADR-005: Human-in-the-loop for Sensitive Actions

## Status
Accepted

## Context
AI-powered systems can produce false positives that might damage reputation (e.g., sending a weird outreach message or incorrectly marking a job as rejected).

## Decision
All sensitive actions (sending outreach, applying to a job, final rejection/offer status) require **explicit human confirmation**. The system only *suggests* state changes.

## Consequences
- **Pros:** High safety, human remains in control, prevents automated "spamming".
- **Cons:** Slightly slower than fully autonomous systems, requires user attention.
