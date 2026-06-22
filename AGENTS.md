# Agent Context

## Project Background

SIVA is forked from xiangshanAIA. The project goal is to build a flexible and low-overhead secure interrupt virtualization architecture.

The upstream xiangshanAIA code is based on the RISC-V Advanced Interrupt Architecture (AIA). Its main security-oriented extension is an additional set of APLIC and IMSIC logic dedicated to TEE environments. That TEE-specific path can be enabled or disabled through the `HasTEEIMSIC` parameter.

The SIVA approach should be understood as modifying and extending AIA itself, rather than only adding a separate TEE-only duplicate path. When analyzing or changing the code, prefer designs that preserve the AIA programming model while adding secure interrupt virtualization behavior with minimal extra hardware cost.

## Code Orientation

- `src/main/scala/APLIC.scala` implements the APLIC and MSI generation path.
- `src/main/scala/IMSIC.scala` implements IMSIC interrupt files, CSR-facing behavior, and MSI receive logic.
- `src/main/scala/IMSICParameters.scala` contains the global IMSIC-related parameter key, including `HasTEEIMSIC`.
- Tests for APLIC and IMSIC behavior live under `test/aplic` and `test/imsic`.

## Design Notes For Agents

- Treat xiangshanAIA's `HasTEEIMSIC` mechanism as important prior art, but do not assume SIVA should always duplicate APLIC/IMSIC blocks for TEE.
- For SIVA changes, first ask whether the behavior can be represented as an AIA-compatible extension to interrupt files, MSI address decoding, CSR selection, or interrupt-source attributes.
- Keep the secure interrupt virtualization goal explicit when explaining changes: separate secure and non-secure interrupt delivery where needed, while avoiding unnecessary duplication of the whole interrupt subsystem.
