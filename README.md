# DIIA

DIIA is built on the RISC-V AIA baseline and extends the interrupt programming model with a security-oriented, domain-aware design for interrupt virtualization and routing.

This branch focuses on a simple, prototype-oriented implementation rather than a full duplicate interrupt subsystem. The goal is to keep the clean AIA structure while adding the domain selection and isolation needed for secure multi-domain interrupt handling.


## Design goals

- Keep the AIA baseline intact where possible.
- Add domain-aware interrupt selection without duplicating the whole interrupt subsystem.
- Support a simple 2-domain model for:
  - IMSIC interrupt-file banking
  - MSI address decoding
  - CSR selection
  - active-domain state similar to `msdcfg.SDICN`
- Keep M-level interrupt delivery singular and always active.

## IMSIC changes

The IMSIC logic is extended to support domain-aware behavior in a minimal and localized way:

- Interrupt-file banking based on selected domain
- CSR-facing routing and domain selection
- MSI receive handling with domain-aware dispatch
- Active-domain state tracking for interrupt delivery
- Isolation between domains to avoid cross-domain MSI routing leakage
- Validation of invalid domain selection and pending summary behavior

In short, IMSIC remains the core interrupt file and CSR-facing mechanism, but it now carries the domain concept needed for secure interrupt virtualization.

## APLIC changes

The APLIC path is adjusted to integrate with the same domain-aware model:

- Domain-aware MSI generation and routing
- Address decoding tied to the selected domain
- Routing and pending/summary behavior kept isolated per domain
- Localized changes to the existing AIA programming model, without introducing a separate legacy duplicate path

This keeps the interrupt delivery flow consistent while making it possible to model per-domain interrupt ownership and dispatch.

## Repository structure

- `src/main/scala/`: Chisel RTL for the project
  - `APLIC.scala`: APLIC domain handling and MSI generation
  - `IMSIC.scala`: IMSIC interrupt-file, CSR, and MSI receive logic
- `test/aplic/`: APLIC-focused tests
- `test/imsic/`: IMSIC-focused tests
- `test/integration/`: cross-module validation
- `docs/`: architecture notes and diagrams
- `reference/`: external specifications and reference material

## Status

This repository is a focused prototype aimed at the security-oriented interrupt virtualization problem. It prioritizes correctness, minimal scope, and compatibility with the baseline AIA architecture rather than broad subsystem duplication.
