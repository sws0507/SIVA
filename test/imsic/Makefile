TOPLEVEL = TLAIA
VERILOG_SOURCES += $(addprefix $(realpath ../../gen)/, $(shell cat ../../gen/filelist.f))
SIM_BUILD = ../sim_build
COCOTB_TEST_MODULES = imsic_m_mode,imsic_csr,imsic_supervisor,imsic_dynamic_tag,imsic_illegal,imsic_readonly
include ../Makefile.common

IMSIC_TESTS = \
	imsic_m_mode_interrupt_test \
	imsic_csr_access_test \
	imsic_supervisor_and_vs_test \
	imsic_dynamic_tag_s_file_test \
	imsic_dynamic_tag_vs_file_test \
	imsic_dynamic_tag_csr_guard_test \
	imsic_illegal_iselect_test \
	imsic_illegal_vgein_test \
	imsic_illegal_wdata_op_test \
	imsic_illegal_privilege_test \
	imsic_eip0_readonly_zero_test

IMSIC_SELECTED_TESTS = $(if $(COCOTB_TEST_FILTER),$(COCOTB_TEST_FILTER),$(IMSIC_TESTS))

.DEFAULT_GOAL := imsic-waves

.PHONY: imsic-waves clean-waves waves results

.FORCE:

imsic-waves: $(addprefix wave-,$(IMSIC_SELECTED_TESTS))

waves results:
	mkdir -p $@

wave-%: .FORCE | waves results
	$(MAKE) sim COCOTB_TEST_FILTER=$* WAVE_FILE=waves/$*.fst COCOTB_RESULTS_FILE=results/$*.xml

clean-waves:
	rm -rf waves results
