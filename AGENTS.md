# Repository Guidelines

## Project Structure and Module Organization

SIVA is a Chisel implementation of RISC-V AIA with security-oriented interrupt virtualization work on this branch. Core RTL lives in `src/main/scala/`: `APLIC.scala` handles APLIC domains and MSI generation, `IMSIC.scala` handles interrupt files, CSR-facing behavior, and MSI receive logic, and `IMSICParameters.scala` carries global IMSIC options such as `HasTEEIMSIC`. Tests live under `test/aplic`, `test/imsic`, `test/integration`, and `test/axi`. Architecture notes and diagrams live in `docs/`; external specifications are kept in `reference/`.

## Simple Smmtt Scope

This branch targets a simple Smmtt/Smsdia prototype. Prefer extending the AIA programming model instead of duplicating the whole interrupt subsystem. For a 2-domain design, model domain selection around IMSIC interrupt-file banking, MSI address decoding, CSR selection, and `msdcfg.SDICN`-style active-domain state. Keep M-level interrupt delivery singular and always active. Treat `HasTEEIMSIC` as prior art, but avoid making it the default design unless the change specifically needs a separate TEE IMSIC instance.

Before making Smmtt changes, check `agents/PLAN.md` for the active plan and follow entries marked as `in progress` unless the user says otherwise.

## Build, Test, and Development Commands

Use `nix-shell` or direnv before building. Run `make -j` to generate Verilog with Mill and run all Cocotb tests. Use focused targets while iterating:

```bash
make run-imsic
make run-aplic
make run-integration
make run-axi
make clean
```

`make doc` rebuilds mdBook documentation and generated diagrams.

## Coding Style and Naming Conventions

Follow the existing Scala/Chisel style: two-space indentation, `camelCase` values, `PascalCase` classes/modules, and descriptive signal names. Keep hardware changes localized to the relevant APLIC/IMSIC path. Use small helper functions for repeated address or interrupt-file index calculations, but avoid broad refactors during feature work.

## Testing Guidelines

Tests use Cocotb with Verilator. Add focused tests near the affected component: IMSIC CSR/MSI behavior in `test/imsic/main.py`, APLIC routing in `test/aplic/main.py`, and cross-module behavior in `test/integration/main.py`. For Smmtt work, cover both domains, invalid domain selection, pending summary behavior, and MSI routing isolation.

## Commit and Pull Request Guidelines

Existing history uses short imperative messages such as `Test update` and scoped messages like `feat(IMSIC): ...`. Prefer concise scoped commits, for example `feat(IMSIC): add simple SDICN domain select`. PRs should describe the architecture intent, list tests run, and call out compatibility risks with existing AIA behavior.
