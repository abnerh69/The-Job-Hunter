# ADR-001: Streamlit for Dashboard

## Status
Accepted

## Context
We need a dashboard to visualize job search progress, manage applications, and interact with the system (e.g., outreach management).

## Decision
We chose **Streamlit** as the primary framework for the dashboard instead of a traditional FastAPI + Vue/React stack.

## Consequences
- **Pros:** Extremely fast development cycle, Python-native (no context switching), built-in components for data visualization.
- **Cons:** Limited customization of layout compared to custom CSS/JS, state management can be tricky for complex interactions, not designed for high-concurrency public-facing apps (which is fine for a personal tool).
