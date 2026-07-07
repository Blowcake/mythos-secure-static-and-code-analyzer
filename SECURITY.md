# Security Policy

We take the security of the AutoIt Static Analyzer seriously. This document outlines our vulnerability reporting process and service level agreements (SLAs) for security fixes.

---

## 1. Supported Versions

Security updates are actively applied to the following versions:

| Version | Supported | Notes |
| :--- | :--- | :--- |
| `0.1.x` | Yes | Active stable branch |

---

## 2. Reporting a Vulnerability

If you discover a security vulnerability in the analyzer, please do NOT file a public issue on GitHub. Instead, report it privately:
- Use GitHub private vulnerability reporting when available, or contact the repository maintainers privately before public disclosure.
- Include a detailed description of the vulnerability, steps to reproduce, and a proof-of-concept (PoC) if possible.

We will acknowledge receipt of your report within **2 business days** and provide a status update on triage and planned fixes.

---

## 3. Vulnerability Classification & SLAs

We categorize security issues and commit to resolving them according to the following SLAs:

| Severity | Definition | Fix Target SLA |
| :--- | :--- | :--- |
| **P0 (Critical)** | Core execution flow or sandbox validation bypass (e.g. remote execution or command injection in settings GUI). | **Within 7 days** of confirmation |
| **P1 (High)** | Denial of service (DoS) crashes during parsing loops. | **Within 14 days** of confirmation |
| **P2 (Medium)** | Mild logic leaks without immediate exploitability. | **Within 30 days** of confirmation |
