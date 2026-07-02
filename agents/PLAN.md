# Plan

This file records plans and their status. Valid statuses are: completed, in progress, not started, and discarded.

Unless explicitly stated otherwise, focus only on plans marked as in progress and ignore plans with other statuses.

## Plans

1. Completed: Remove the original `HasTEE` code and keep a clean AIA baseline for future modifications.
2. Completed: Implement a DynamicTag-based simple Smmtt prototype without duplicating the full IMSIC.
   - IMSIC keeps the external AIA guestID layout unchanged, while adding an internal confidential S `IntFile`.
   - IMSIC checks MSI address tags, VS interrupt-file domain bitmap state, and the current `sec` input for CSR-side access control.
   - APLIC adds an `IntSource` bitmap and tags confidential MSI writes with the `0x80` page offset.
   - Verified with `mill TLAIA`, `make run-imsic`, `make run-aplic`, `make run-integration`, `mill AXI4AIA`, and `make run-axi`.
