# Top-level ENO Makefile
#
# Builds libraries first, then tools, then productions.
# Each subdirectory has its own Makefile and is independently buildable.

# Library order matters: gfx/siftr/fx/io depend on core and crest.
LIBS  = lib/core lib/crest lib/io lib/siftr lib/fx lib/gfx
TOOLS = tools/carve tools/glint tools/smolr
PRODS = prods/desert-monument

ALL_DIRS = $(LIBS) $(TOOLS) $(PRODS)

.PHONY: all test clean libs tools prods riscv $(ALL_DIRS)

all: libs tools prods

libs:  $(LIBS)
tools: libs $(TOOLS)
prods: libs $(PRODS)

# Recursive target dispatch.
$(ALL_DIRS):
	@if [ -f $@/Makefile ]; then \
	    $(MAKE) -C $@; \
	else \
	    echo "skipping $@ (no Makefile yet)"; \
	fi

test:
	@for d in $(LIBS); do \
	    if [ -f $$d/Makefile ]; then \
	        $(MAKE) -C $$d test || exit 1; \
	    fi; \
	done

clean:
	@for d in $(ALL_DIRS); do \
	    if [ -f $$d/Makefile ]; then \
	        $(MAKE) -C $$d clean; \
	    fi; \
	done

riscv:
	@for d in $(LIBS); do \
	    if [ -f $$d/Makefile ]; then \
	        $(MAKE) -C $$d riscv || exit 1; \
	    fi; \
	done
