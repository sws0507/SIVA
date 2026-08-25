TOPLEVEL = TLAIA
SIM ?= verilator
TOPLEVEL_LANG ?= verilog
SIVA_ROOT ?= $(realpath ../..)
export PATH := $(SIVA_ROOT)/.venv/bin:$(PATH)
override PYTHON_BIN := $(SIVA_ROOT)/.venv/bin/python
VERILOG_SOURCES += $(addprefix $(realpath ../../gen)/, $(shell cat ../../gen/filelist.f))
SIM_BUILD = ../sim_build
COCOTB_TEST_MODULES = main
WAVE_FILE ?= waves/dtid_cross_domain_matrix.fst
COCOTB_RESULTS_FILE ?= results/dtid_cross_domain_matrix.xml
EXTRA_ARGS += --trace --trace-fst --trace-structs
SIM_ARGS += --trace-file $(WAVE_FILE)

.DEFAULT_GOAL := experiment

.PHONY: experiment waves results clean-results

experiment: waves results
	$(MAKE) sim WAVE_FILE=$(WAVE_FILE) COCOTB_RESULTS_FILE=$(COCOTB_RESULTS_FILE)

waves results:
	mkdir -p $@

clean-results:
	rm -rf waves results

include $(shell $(SIVA_ROOT)/.venv/bin/cocotb-config --makefiles)/Makefile.sim
