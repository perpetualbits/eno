#!/usr/bin/env bash
# survey/scripts/build-survey.sh
#
# Build the cartesian product of (test, ISA tier, flag combo).
# Driven by the Makefile via env vars:
#
#   TESTS         space-separated test names (no .c)
#   TIERS         space-separated -march strings
#   FLAGCOMBOS    relax-plt | norelax-plt | relax-noplt | norelax-noplt
#   CFLAGS_COMMON shared C flags
#   BUILD         output directory (typically tools/smolr/build/survey)
#   GCC           C compiler (cross or native)

set -u

: "${TESTS:?}"
: "${TIERS:?}"
: "${FLAGCOMBOS:?}"
: "${CFLAGS_COMMON:?}"
: "${BUILD:?}"
: "${GCC:?}"

# An expanded ISA fallback for toolchains that reject -march=rva23u64.
# Based on the RVA23U64 mandatory user-mode extensions list.
RVA23_FALLBACK="rv64gcv_zicsr_zifencei_zihintpause_zba_zbb_zbs_zcb_zicond_zfhmin_zfa_zvbb_zvkt_zihintntl"

# Cache "does this toolchain accept -march=X?" results.
declare -A ARCH_OK

march_accepted() {
    local arch="$1"
    if [ -n "${ARCH_OK[$arch]:-}" ]; then
        return "${ARCH_OK[$arch]}"
    fi
    local tmp log
    tmp="$(mktemp -d)"
    log="$tmp/log"
    printf 'int main(void){return 0;}\n' > "$tmp/t.c"
    if "$GCC" -march="$arch" -mabi=lp64d -c "$tmp/t.c" -o "$tmp/t.o" \
              >"$log" 2>&1; then
        ARCH_OK[$arch]=0
    else
        ARCH_OK[$arch]=1
    fi
    rm -rf "$tmp"
    return "${ARCH_OK[$arch]}"
}

# Resolve a tier name to the actual -march to pass to gcc.
resolve_tier() {
    local tier="$1"
    if march_accepted "$tier"; then
        echo "$tier"
        return
    fi
    if [ "$tier" = "rva23u64" ]; then
        if march_accepted "$RVA23_FALLBACK"; then
            echo "$RVA23_FALLBACK"
            return
        fi
    fi
    echo ""  # signal: this tier is unbuildable
}

# Flag-combo decoder.
flags_for() {
    local combo="$1"
    case "$combo" in
        relax-plt)      echo "-mrelax" ;;
        norelax-plt)    echo "-mno-relax" ;;
        relax-noplt)    echo "-mrelax -fno-plt" ;;
        norelax-noplt)  echo "-mno-relax -fno-plt" ;;
        *) echo "UNKNOWN_FLAG_COMBO_$combo" ;;
    esac
}

# Per-test link recipe. Most tests link with default libc. 03-call-libm
# also needs -lm. The link is optional: if it fails (e.g. on a cross host
# without a sysroot containing the right libraries), we keep the .o so the
# relocation inspection still works.
extra_link_flags_for() {
    case "$1" in
        03-call-libm) echo "-lm" ;;
        *) echo "" ;;
    esac
}

mkdir -p "$BUILD"
PASS=0; FAIL=0; SKIP=0

echo "Building survey corpus..."
for test in $TESTS; do
    src="survey/tests/$test.c"
    if [ ! -f "$src" ]; then
        echo "  ERROR: missing $src"
        FAIL=$((FAIL+1))
        continue
    fi

    for tier in $TIERS; do
        march="$(resolve_tier "$tier")"
        if [ -z "$march" ]; then
            echo "  SKIP  $test / $tier (toolchain rejects -march)"
            SKIP=$((SKIP+1))
            continue
        fi

        for combo in $FLAGCOMBOS; do
            cflags_extra="$(flags_for "$combo")"
            link_extra="$(extra_link_flags_for "$test")"

            stem="$BUILD/$test-$tier-$combo"

            # Always produce the .o so we can read object-level relocations.
            obj="$stem.o"
            if "$GCC" -march="$march" -mabi=lp64d \
                      $CFLAGS_COMMON $cflags_extra \
                      -c "$src" -o "$obj" \
                      2> "$stem.compile.log"; then
                :
            else
                echo "  FAIL  obj  $test / $tier / $combo"
                FAIL=$((FAIL+1))
                continue
            fi

            # Attempt to link. Allowed to fail; just record it.
            elf="$stem.elf"
            if "$GCC" -march="$march" -mabi=lp64d \
                      $CFLAGS_COMMON $cflags_extra \
                      "$src" -o "$elf" $link_extra \
                      2> "$stem.link.log"; then
                PASS=$((PASS+1))
            else
                # Link failure is interesting but not fatal at survey stage.
                rm -f "$elf"
                PASS=$((PASS+1))
            fi
        done
    done
done

echo
echo "Survey build complete: $PASS pass, $FAIL fail, $SKIP skipped."
echo "Artifacts in: $BUILD/"
[ "$FAIL" -eq 0 ]
