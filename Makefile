.NOTINTERMEDIATE:
# export MILL_JVM_OPTS="-Xmx16G"
SIVA_ROOT := $(CURDIR)
CHISEL_FIRTOOL_PATH ?= /Users/sunweishi/Library/Caches/org.chipsalliance.llvm-firtool/1.62.0/bin/
XDG_CACHE_HOME ?= $(SIVA_ROOT)/.cache
COURSIER_CACHE ?= $(SIVA_ROOT)/.cache/coursier
MILL_LOCAL_HOME ?= $(SIVA_ROOT)/.home
PYTHONPATH := $(SIVA_ROOT)/test:$(PYTHONPATH)
PATH := $(SIVA_ROOT)/.venv/bin:$(SIVA_ROOT):$(CHISEL_FIRTOOL_PATH):$(PATH)
export CHISEL_FIRTOOL_PATH XDG_CACHE_HOME COURSIER_CACHE MILL_LOCAL_HOME PYTHONPATH PATH

testcases=$(shell ls test/*/main.py | awk -F '/' '{print $$2}')
default: $(addprefix run-,$(testcases))

gen=gen/filelist.f
gen_axi=gen_axi/filelist.f
$(gen): $(wildcard src/main/scala/*)
	$(SIVA_ROOT)/.venv/bin/mill TLAIA
$(gen_axi): $(wildcard src/main/scala/*)
	$(SIVA_ROOT)/.venv/bin/mill AXI4AIA

compile=test/sim_build/Vtop
compile_axi=test/sim_build_axi/Vtop
$(compile): $(gen)
	make -C test/integration ../sim_build/Vtop
$(compile_axi): $(gen_axi)
	make -C test/axi ../sim_build_axi/Vtop

# let the `make run-...` can be auto completed
define RUN_TESTCASE =
run-$(1):
endef
$(foreach testcase,$(testcases),$(eval $(call RUN_TESTCASE,$(testcase))))
# `ulimit -s` make sure stack size is enough
run-%: test/%/main.py $(compile)
	# ulimit -s 211487 && make -C test/$(subst run-,,$@)
	(ulimit -s 211487 2>/dev/null || true) && make -C test/$(subst run-,,$@)
run-axi: test/axi/main.py $(compile_axi)
	# ulimit -s 211487 && make -C test/$(subst run-,,$@)
	(ulimit -s 211487 2>/dev/null || true) && make -C test/$(subst run-,,$@)

clean:
	rm -rf out/ gen*/ test/sim_build*/

################################################################################
# doc
################################################################################
MDs=$(shell find docs/ -name "*.md") \
		$(patsubst src/main/scala/%.scala,docs/%_scala.md,$(wildcard src/main/scala/*.scala))
PYSVGs=$(subst _dot.py,_py.svg,$(shell find docs/ -name "*_dot.py"))
# DRAWIOSVGs=$(subst .drawio,.svg,$(shell find docs/ -name "*.drawio"))
DOTSVGs=$(subst .dot,.svg,$(shell find docs/ -name "*.dot"))
# doc: $(MDs) $(PYSVGs) $(DRAWIOSVGs) $(DOTSVGs)
# 	mdbook build
doc: $(MDs) $(PYSVGs) $(DOTSVGs)
	mdbook build
docs/images/arch_configure_py.dot: docs/images/arch_common.py
docs/images/arch_interrupt_py.dot: docs/images/arch_common.py
docs/images/example_py.dot: docs/images/example_common.py
docs/images/example-axi_py.dot: docs/images/example_common.py
%_py.dot: %_dot.py
	python3 $<
%.svg: %.dot
	dot -Tsvg $< -o $@
	# css can only recognize intrinsic size in px
	# https://developer.mozilla.org/en-US/docs/Glossary/Intrinsic_Size
	sed -i 's/\([0-9]\+\)pt/\1px/g' $@
# %.svg: %.drawio
# 	drawio -x -f svg $<
docs/%_scala.md: src/main/scala/%.scala
	markcode $< > $@
