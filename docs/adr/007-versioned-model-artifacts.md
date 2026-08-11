# ADR 007: Load checksum-verified model artifacts at startup

- Status: accepted
- Date: 2026-08-11

## Context

The v0.2 API trained both models during application startup. That made cold starts slow and,
more importantly, allowed the deployed model and thresholds to depend on the runtime training
environment. A model version string alone did not identify the fitted estimators or policy.

## Alternatives considered

1. Keep startup training. Simple, but it is not a controlled deployment mechanism.
2. Add a hosted model registry. Operationally realistic, but it would make the local demo
   depend on external infrastructure and credentials.
3. Check in a versioned, self-contained bundle with a human-readable manifest and checksum.

## Decision

Use option 3. `make artifacts` deterministically trains the models and writes the estimators,
validation records, active thresholds, and assumptions to a Joblib bundle. The adjacent JSON
manifest records source commit, training configuration, dependency versions, ordered feature
contract, and SHA-256 checksum. Startup refuses missing, modified, or feature-incompatible
artifacts. Retraining is now an explicit build step rather than an API side effect.

## Advantages

- A runtime model is identified by immutable bytes and provenance, not only a name.
- Startup no longer pays the training cost.
- A fresh clone and Docker image use the same champion, challenger, and policy.
- Checksum and feature-order validation fail closed on common packaging errors.

## Disadvantages

- The binary bundle increases repository size.
- Joblib loading requires trusted artifacts and compatible Python library versions.
- This is not a full registry with signing, approval workflow, remote storage, or rollback API.

## Consequences

The checked artifact is appropriate for this reproducible reference project, but it must not
be described as an enterprise model registry. A later external registry can preserve this
manifest contract while replacing local bundle discovery and adding cryptographic signing.
