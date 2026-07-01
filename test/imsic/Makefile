TOPLEVEL = TLAIA
COCOTB_TEST_MODULES = imsic_m_mode,imsic_csr,imsic_supervisor,imsic_smmtt,imsic_illegal,imsic_readonly
IMSIC_TESTS = \
	imsic_m_mode_interrupt_test \
	imsic_csr_access_test \
	imsic_supervisor_and_vs_test \
	imsic_smmtt_bank_selection_test \
	imsic_smmtt_inactive_domain1_vs_msi_test \
	imsic_smmtt_inactive_domain0_vs_msi_test \
	imsic_illegal_iselect_test \
	imsic_illegal_vgein_test \
	imsic_illegal_wdata_op_test \
	imsic_illegal_privilege_test \
	imsic_eip0_readonly_zero_test
ifneq ($(strip $(COCOTB_TEST_FILTER)),)
IMSIC_SELECTED_TESTS = $(COCOTB_TEST_FILTER)
else
IMSIC_SELECTED_TESTS = $(IMSIC_TESTS)
endif
IMSIC_WAVE_DIR ?= waves
IMSIC_RESULT_DIR ?= results
VERILOG_SOURCES += $(addprefix $(realpath ../../gen)/, $(shell cat ../../gen/filelist.f))
SIM_BUILD = ../sim_build

.DEFAULT_GOAL := imsic-waves

.PHONY: imsic-waves clean-waves $(addprefix wave-,$(IMSIC_TESTS))
imsic-waves: $(addprefix wave-,$(IMSIC_SELECTED_TESTS))

define IMSIC_WAVE_RULE
wave-$(1):
	mkdir -p $$(IMSIC_WAVE_DIR) $$(IMSIC_RESULT_DIR)
	$$(MAKE) sim COCOTB_TEST_FILTER=$(1) WAVE_FILE=$$(IMSIC_WAVE_DIR)/$(1).fst COCOTB_RESULTS_FILE=$$(IMSIC_RESULT_DIR)/$(1).xml
endef
$(foreach test,$(IMSIC_TESTS),$(eval $(call IMSIC_WAVE_RULE,$(test))))

clean-waves:
	rm -rf $(IMSIC_WAVE_DIR) $(IMSIC_RESULT_DIR)

include ../Makefile.common
