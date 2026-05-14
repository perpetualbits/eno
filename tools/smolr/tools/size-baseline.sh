#!/usr/bin/env bash
# tools/size-baseline.sh
#
# Measure normal-ld output sizes (and optionally UPX-packed sizes) for the
# survey corpus's linked ELFs. This is the "what SMOLR has to beat" number.
#
# Reads env from the Makefile: TESTS, TIERS, BUILD, SURVEY, GCC, STRIP.

set -u

: "${TESTS:?}"
: "${TIERS:?}"
: "${BUILD:?}"
: "${SURVEY:?}"
: "${GCC:?}"
: "${STRIP:?}"

have() { command -v "$1" >/dev/null 2>&1; }

printf "%-26s %-26s %12s %12s %12s\n" \
    "test" "tier" "linked" "stripped" "upx"

for test in $TESTS; do
    for tier in $TIERS; do
        # Use the most-relaxed, default-PLT, with-relax build for this baseline.
        elf="$SURVEY/$test-$tier-relax-plt.elf"
        if [ ! -f "$elf" ]; then
            printf "%-26s %-26s %12s %12s %12s\n" \
                "$test" "$tier" "(no link)" "-" "-"
            continue
        fi

        sz_linked=$(stat -c '%s' "$elf")

        # Strip into a temp file so we can compare.
        stripped="$BUILD/baseline-stripped-$test-$tier.elf"
        cp "$elf" "$stripped"
        "$STRIP" "$stripped" 2>/dev/null || true
        sz_stripped=$(stat -c '%s' "$stripped")

        if have upx; then
            upxed="$BUILD/baseline-upx-$test-$tier.elf"
            cp "$stripped" "$upxed"
            # UPX needs --best for maximum compression; suppress output.
            if upx --best -q "$upxed" >/dev/null 2>&1; then
                sz_upx=$(stat -c '%s' "$upxed")
            else
                sz_upx="(upx failed)"
            fi
        else
            sz_upx="(no upx)"
        fi

        printf "%-26s %-26s %12s %12s %12s\n" \
            "$test" "$tier" "$sz_linked" "$sz_stripped" "$sz_upx"
    done
done
