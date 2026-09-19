# Duke Kunshan Signature Work Project

This repository contains my undergraduate Signature Work project.

## Project

I am developing a software-focused Creative/Design Signature Work involving:

- Agentic Retrieval-Augmented Generation (RAG)
- runtime evaluation
- failure diagnosis
- adaptive recovery
- recovery verification
- benchmarking
- trajectory/trace visualization

The central workflow is:

Agent acts
→ evaluation
→ failure diagnosis
→ recovery selection
→ recovery
→ verification
→ accept / retry / abstain

The project investigates whether evaluation can help an Agentic RAG system identify failures, choose appropriate corrective actions, and verify whether those actions actually improve the result.

The primary deliverable is working software.

## Academic Context

This is an academic Signature Work project. I still own the claims, the interpretation of results, and the conclusions.

**Software construction (updated 2026-09-19):** Cursor should have **utmost freedom to build**. It may redesign and implement the product from my vision without asking permission at every architecture, UI, or stack choice. Older “do not autonomously redesign / confirm before building” instructions are revoked for engineering work.

I still need to be able to explain the finished system. Cursor must not fabricate experimental results, citations, or thesis conclusions.

## Engineering Principles

Build the product I am picturing. Prefer working software that matches the vision over protecting the current issue list or keeping V1 small.

Useful habits, not blockers: understandable code, tests where they catch real breakage, reproducible experiments, do not overwrite historical `experiments/results/` snapshots.

Do not add billing, enterprise SSO, or unrelated commercial SaaS unless I ask.