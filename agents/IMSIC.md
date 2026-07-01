# IMSIC TileLink Module Notes

This note describes the roles of `TLIMSIC`, `TLRegIMSIC_WRAP`, and `TLRegIMSIC` in the current AIA branch. The focus is the TileLink path that receives memory-mapped MSI writes and delivers them to an IMSIC interrupt file.

## Module Hierarchy

For each hart, the current top level instantiates one `TLIMSIC`.

```text
TLIMSIC
  |-- IMSIC
  `-- TLRegIMSIC_WRAP
        `-- TLRegIMSIC
              `-- RegGen
```

In `Example.scala`, four harts are modeled by creating four `TLIMSIC` instances. Each hart therefore has its own `TLIMSIC`, `TLRegIMSIC_WRAP`, `TLRegIMSIC`, and `IMSIC`.

## TLIMSIC

`TLIMSIC` is the per-hart TileLink IMSIC top module.

It connects two paths:

- CSR path: `fromCSR` and `toCSR` connect directly to the local `IMSIC`.
- MSI memory path: TileLink writes enter through `TLRegIMSIC_WRAP`, become `msiio`, and then feed the local `IMSIC`.

`TLIMSIC` also separates clock domains. The TileLink register side runs on `soc_clock`, while the IMSIC CSR side runs on the module `clock`.

## TLRegIMSIC_WRAP

`TLRegIMSIC_WRAP` is the TileLink bus shell around `TLRegIMSIC`.

Its main responsibilities are:

- Expose `imsic_xbar1to2` so the top level can connect APLIC or CPU TileLink traffic to this hart's IMSIC.
- Declare the memory-mapped IMSIC address windows:
  - `params.mAddr` for the machine interrupt file region.
  - `params.sgAddr` for the supervisor and guest interrupt file region.
- Bridge the external TileLink node into the internal `TLRegIMSIC`.

This wrapper does not interpret interrupt IDs or update pending bits. It only provides the address-visible bus entry for one hart's IMSIC.

## TLRegIMSIC

`TLRegIMSIC` is the TileLink register-mapped MSI receiver.

It contains:

- `TLRegMapperNode` entries for the M and S/VS interrupt-file regions.
- `RegGen`, which converts a memory write address and write data into an internal MSI payload.
- A FIFO that buffers generated MSI payloads before forwarding them to the IMSIC clock domain through `msiio`.

For a memory write:

```text
TileLink address -> interrupt file index
TileLink data    -> interrupt identity
```

The generated internal payload is:

```text
msiio.data = { fileIndex, interruptId }
```

## MSI Write Flow

An APLIC MSI write follows this path:

```text
APLIC Domain
  -> TLAPLIC TileLink Put
  -> system interconnect / TLMap
  -> TLRegIMSIC_WRAP
  -> TLRegIMSIC
  -> RegGen
  -> FIFO
  -> msiio
  -> IMSICGateWay
  -> selected IntFile
```

APLIC encodes the target interrupt file in the MSI address and the interrupt identity in the MSI data. `RegGen` consumes the address offset to compute `fileIndex`, keeps the low `imsicIntSrcWidth` bits of the data as `interruptId`, and emits `{fileIndex, interruptId}` to the IMSIC.

## Smmtt Implication

For a simple Smmtt design with multiple IMSIC banks per hart, these TileLink shell modules should usually remain per hart rather than being replicated per IMSIC bank.

The preferred direction is:

```text
one TLIMSIC per hart
one TLRegIMSIC_WRAP per hart
one TLRegIMSIC per hart
multiple IMSIC banks inside the hart
```

The Smmtt extension should enlarge the S/VS address region and extend `RegGen` so the MSI address can encode both the target IMSIC bank and the local interrupt-file index.
