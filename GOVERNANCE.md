# Project Governance

This document describes the project governance, roles, versioning release policy, dependency update policy, and issue triage workflow for the AutoIt Static Analyzer.

---

## 1. Project Roles

To ensure code quality and maintain the analyzer's accuracy, we define two primary roles:

### 1.1 Maintainers
- **Responsibilities**: Code review, merging pull requests, releasing new versions, triaging issues, managing security reports, and ensuring strict adherence to coding rules and original Au3Check parity.
- **Access**: Full write permissions to the repository and authority to sign off on releases.
- **Current Maintainers**:
  - Harald Frank (@haraldfrank)

### 1.2 Contributors
- **Responsibilities**: Finding bugs, proposing enhancements, submitting pull requests, and participating in design discussions.
- **Requirements**: All contributions must pass the build/validation pipeline (`.\build.ps1`) with 0 warnings/errors and pass all golden parity tests.

---

## 2. Versioning & Release Policy

We follow **Semantic Versioning 2.0.0 (SemVer)** for all analyzer releases:
- **Major Version (`X.0.0`)**: Incremented when breaking changes are introduced to the public command line options, exit codes, or diagnostic formats.
- **Minor Version (`0.Y.0`)**: Incremented when new backward-compatible warnings or options are added.
- **Patch Version (`0.0.Z`)**: Incremented for backward-compatible bug fixes, performance improvements, and documentation updates.

### Version Upgrades
Version increments must be made via the `.\bump.ps1` script (e.g. `.\bump.ps1 patch`). This ensures the `project.json` version is incremented safely.

---

## 3. Dependency Update Policy

The analyzer is designed to be highly stable with minimal external dependencies:

1. **Python Runtime**: The analyzer targets standard Python 3.x installations. We avoid external Python package dependencies to keep deployment as zero-config as possible.
2. **AutoIt Integration**: The wrapper and GUI configurations interface directly with standard AutoIt v3.x installations.

---

## 4. Issue Triage and Priority SLA

Issues submitted to the repository must be triaged within **2 business days** and labeled accordingly.

### 4.1 Issue Labels

We use the following label taxonomy:
- **Types**: `bug`, `enhancement`, `question`, `documentation`.
- **Status**: `needs confirmation`, `needs repro`, `ready for work`, `good first issue`, `help wanted`.
- **Priorities**:
  - `P0 (Critical)`: Severe crash, security bypass, or complete blockages. (Fix SLA: 7 days)
  - `P1 (High)`: Broken core method (e.g. false positives on standard library functions). (Fix SLA: 14 days)
  - `P2 (Medium)`: Minor parser deviation or non-critical error logging issue. (Fix SLA: 30 days)
  - `P3 (Low)`: Documentation typos or cosmetic improvements. (Fix SLA: Next release)
