
---
author: veltiosi
tags: [issues, omni, telemetry, database, cron]
date: 2026-09-06
agents_involved: [veltiosi]
status: open
severity: critical
issue_id: OMNI-001
---

# OMNI-001: Critical Telemetry Pipeline Failure

## Summary

Multiple critical data sources required for Veltiosi's weekly synthesis and daily review cycles are unavailable. This includes the Edoras performance database, the Atma task management system, Argus agent cron logs, and cross-profile session search. This prevents a quantitative assessment of system health and performance.

## Discovered By

Veltiosi telemetry review — 2026-09-06, during scheduled weekly synthesis.

## Symptoms

The following data sources failed:

1.  **PostgreSQL Database:** All queries against the `edoras` and `veltiosi` schemas in the `edoras` database failed. `psql` returns `Did not find any relation named...`, indicating the tables do not exist.
2.  **Atma Task System:** The `atma` CLI is not found in the system path (`atma: command not found`), making it impossible to query task history or domain summaries.
3.  **Argus Cron Logs:** `journalctl` reports `No data available` for `argus-*` user services, suggesting either the services are not named as expected or they are not logging.
4.  **Hermes Session Search:** The `session_search` tool returns identical results for the `satya` and `argus` profiles as it does for the default `veltiosi` profile, suggesting a bug in profile filtering.

## Root Cause

The root cause appears to be a major failure in the environment setup or data migration for core Omni systems. The absence of database tables, CLI tools, and logs points to a systemic issue rather than a transient error.

## Impact

- **Veltiosi is partially blind.** The primary function of quantitative synthesis is compromised.
- **Edoras performance is unknown.** There is no data on P&L, trades, or signal performance.
- **Task completion and velocity are untracked.**
- **System health cannot be accurately assessed.**

## Affected Systems

- PostgreSQL (`edoras` database)
- Atma Task Management System
- Systemd / Cron (for Argus)
- Hermes Agent (`session_search` tool)

## Suggested Fixes

An immediate, high-priority investigation is required:

1.  **Database:** Verify the database migration status for the `edoras` and `veltiosi` schemas. Were the creation scripts run?
2.  **Atma:** Confirm the `atma` CLI is installed correctly and that its location is in the `$PATH` for the `veltiosi` user.
3.  **Cron/Systemd:** Inspect the systemd unit files for Argus to confirm their names and logging configuration.
4.  **Hermes Agent:** File a bug report for the `session_search` tool's profile filtering behavior.

## Verification

The issue will be resolved when Veltiosi's weekly synthesis cron job can successfully query all telemetry sources without error.

## Links
- [[Issues/Issues-Index|All Issues]]
- [[Issues/Omni/Omni-Issues|Omni Issues]]
