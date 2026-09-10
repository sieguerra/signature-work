# Signature Work V1 Specification

## Working Project

A software platform for reliable Agentic RAG with failure detection, adaptive recovery, and recovery verification.

## Core Problem

Agentic RAG systems can fail at multiple stages, including retrieval, evidence coverage, ranking, generation, citations, and stopping decisions.

The system should investigate whether evaluation can identify selected failures, guide targeted recovery, and verify whether recovery improved the result.

## V1 Must-Have Components

- baseline RAG
- Agentic RAG
- runtime evaluation
- defined failure taxonomy
- recovery controller
- recovery verification
- trace logging
- working application UI
- benchmark evaluation

## V1 Failure Classes

Confirmed in [ADR 005](decisions/005-failure-taxonomy.md):

- retrieval miss (`retrieval_miss`)
- evidence insufficiency (`evidence_insufficiency`), including corpus-gap
- unsupported generation (`unsupported_generation`)

Deferred, not V1: ranking failure, citation failure, a separate corpus-gap class.

## Candidate Recovery Actions

- rewrite query
- retrieve again
- decompose question
- rerank
- regenerate
- repair response
- abstain
- accept

## Out of Scope Before Final Submission

- billing
- Stripe
- enterprise SSO
- mobile app
- dozens of model providers
- Slack/Gmail integrations
- production-scale infrastructure
- complex organization/team features

## Research Goal

Measure whether evaluation-guided recovery improves reliability compared with simpler RAG configurations and determine its cost/latency tradeoffs.