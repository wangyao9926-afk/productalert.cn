# Observability Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task with tests before implementation.

**Goal:** Make monitoring health actionable by exposing user-scoped scan reliability, failure classifications, queue backlog, and notification delivery backlog in the operations center.

**Architecture:** The FastAPI API reads existing scan-log, scan-job, notification-outbox, and site ownership records and computes a compact summary without schema changes. The existing Operations page consumes that single summary for operational metrics while retaining detailed lists for investigation.

**Tech Stack:** FastAPI, SQLite/PostgreSQL-compatible SQL, Python unittest, React/TypeScript.

## Tasks

- [x] Add an owner-scoped `GET /api/operations/summary` contract with aggregate scan counts, success rate, mean duration, failure categories, queue state, and notification state. Test a known mixed-data case first.
- [x] Add frontend types and request the server summary alongside existing health and list requests. Test that the Operations page consumes the summary rather than recreating it client-side.
- [x] Show mean scan duration, classified failures, queue counts, and notification backlog in the Operations center.
- [x] Run all backend tests, API smoke, frontend build, and UI contract checks; restart local preview services and publish the preview URL.
