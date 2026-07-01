"""IMSIC test entry marker.

The real Cocotb tests are split into focused modules in this directory so that
single-test waveform captures stay short and readable.

Examples:
  make run-imsic
  make run-imsic COCOTB_TEST_FILTER=imsic_smmtt_bank_selection_test

The default IMSIC Makefile runs each focused test separately and writes FST
files under test/imsic/waves/.
"""
