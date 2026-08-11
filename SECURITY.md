# Security policy

## Reporting

Please report suspected vulnerabilities through GitHub's private vulnerability reporting
feature rather than a public issue. Include the affected version, reproduction steps, impact,
and any suggested mitigation. No response-time SLA is promised for this portfolio project.

## Supported version

Only the latest tagged release is supported. The CI dependency audit and CodeQL workflow are
preventive checks, not evidence that the software is free of vulnerabilities.

## Scope warning

Aegis processes synthetic identifiers and has no authentication, authorization, encryption,
PII tokenization, or secret-management layer. Do not expose it to untrusted networks or use it
for real payment data. See `docs/limitations.md` for the full control gap.
