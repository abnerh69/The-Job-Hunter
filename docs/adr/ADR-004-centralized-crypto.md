# ADR-004: Centralized Symmetric Encryption

## Status
Accepted

## Context
The system handles sensitive data such as OAuth tokens for Gmail, which must be protected at rest in the database.

## Decision
We use a centralized utility (`src/jobhunter/crypto.py`) based on `cryptography.fernet` for symmetric encryption and decryption. The encryption key is managed via the `OAUTH_ENCRYPTION_KEY` setting.

## Consequences
- **Pros:** Consistent security posture across the application, easy to rotate keys, standard implementation reduces the risk of crypto-related bugs.
- **Cons:** Loss of the encryption key results in permanent loss of access to encrypted data (requires re-authentication).
