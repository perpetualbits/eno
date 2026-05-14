#!/usr/bin/env bash
# survey/scripts/inspect-all.sh
#
# For every survey artifact, write:
#   <stem>.reloc       readelf -rW output (relocation table)
#   <stem>.disasm      objdump -dr output (disassembly with relocs interleaved)
#   <stem>.dynamic     readelf -d output for the linked ELF, if it exists
#   <stem>.symbols     nm output for the .o
#
# Driven by env vars from the Makefile.

set -u

: "${TESTS:?}"
: "${TIERS:?}"
: "${FLAGCOMBOS:?}"
: "${BUILD:?}"
: "${READELF:?}"
: "${OBJDUMP:?}"
: "${NM:?}"

count=0
for test in $TESTS; do
    for tier in $TIERS; do
        for combo in $FLAGCOMBOS; do
            stem="$BUILD/$test-$tier-$combo"
            obj="$stem.o"
            elf="$stem.elf"

            if [ ! -f "$obj" ]; then
                continue
            fi

            "$READELF" -rW "$obj"  > "$stem.reloc"   2>&1 || true
            "$OBJDUMP" -dr  "$obj" > "$stem.disasm"  2>&1 || true
            "$NM"          "$obj" > "$stem.symbols" 2>&1 || true

            if [ -f "$elf" ]; then
                "$READELF" -d "$elf" > "$stem.dynamic" 2>&1 || true
            fi

            count=$((count+1))
        done
    done
done

echo "Inspected $count survey artifacts."
