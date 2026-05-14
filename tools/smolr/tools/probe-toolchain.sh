#!/usr/bin/env bash
# tools/probe-toolchain.sh
#
# Inspect the locally available RISC-V toolchain and write a report.
# Honors $SMOLR_CROSS as the tool prefix (set by the Makefile via uname -m
# auto-detection; empty on native riscv64, "riscv64-linux-gnu-" otherwise).

set -u

CROSS="${SMOLR_CROSS:-}"
GCC="${CROSS}gcc"
AS="${CROSS}as"
LD="${CROSS}ld"
OBJDUMP="${CROSS}objdump"
READELF="${CROSS}readelf"
NM="${CROSS}nm"
STRIP="${CROSS}strip"
QEMU="qemu-riscv64"
UPX="upx"

have() { command -v "$1" >/dev/null 2>&1; }
section() {
    echo
    echo "=========================================================================="
    echo "  $*"
    echo "=========================================================================="
}

# Try compiling an empty TU under the given -march. Print PASS / FAIL line.
try_march() {
    local arch="$1"
    local tmpdir log
    tmpdir="$(mktemp -d)"
    log="$tmpdir/log"
    printf 'int main(void){return 0;}\n' > "$tmpdir/t.c"
    if "$GCC" -march="$arch" -mabi=lp64d -c "$tmpdir/t.c" -o "$tmpdir/t.o" \
              >"$log" 2>&1; then
        echo "  PASS  -march=$arch"
    else
        echo "  FAIL  -march=$arch"
        sed 's/^/         | /' < "$log" | head -n 4
    fi
    rm -rf "$tmpdir"
}

# Try compiling under -march + extra flags.
try_march_with() {
    local arch="$1" extra="$2"
    local tmpdir log
    tmpdir="$(mktemp -d)"
    log="$tmpdir/log"
    printf 'int main(void){return 0;}\n' > "$tmpdir/t.c"
    if "$GCC" -march="$arch" -mabi=lp64d $extra -c "$tmpdir/t.c" -o "$tmpdir/t.o" \
              >"$log" 2>&1; then
        echo "  PASS  -march=$arch $extra"
    else
        echo "  FAIL  -march=$arch $extra"
        sed 's/^/         | /' < "$log" | head -n 4
    fi
    rm -rf "$tmpdir"
}

section "SMOLR toolchain probe"
echo "Date:         $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Host uname:   $(uname -a)"
echo "Cross prefix: '${CROSS}'   (empty means native riscv64)"

section "Tool presence"
for t in "$GCC" "$AS" "$LD" "$OBJDUMP" "$READELF" "$NM" "$STRIP" "$QEMU" "$UPX"; do
    if have "$t"; then
        printf "  FOUND   %-30s -> %s\n" "$t" "$(command -v "$t")"
    else
        printf "  ABSENT  %s\n" "$t"
    fi
done

if ! have "$GCC"; then
    echo
    echo "ERROR: '$GCC' not found. Install a RISC-V GCC or override SMOLR_CROSS."
    exit 1
fi

section "GCC details"
"$GCC" --version | head -n 2
echo "-- target triple --"
"$GCC" -dumpmachine
echo "-- search paths (truncated) --"
"$GCC" -print-search-dirs | head -n 4

section "Binutils details"
"$AS" --version | head -n 1
"$LD" --version | head -n 1
"$READELF" --version | head -n 1

section "QEMU / UPX"
if have "$QEMU"; then "$QEMU" --version | head -n 1; else echo "qemu-riscv64 not installed"; fi
if have "$UPX";  then "$UPX"  --version | head -n 1; else echo "upx not installed (needed for baseline comparison)"; fi

section "-march acceptance"
echo "Which target tiers does this toolchain accept directly?"
echo
try_march "rv64gc"
try_march "rv64gc_zba_zbb_zbs"
try_march "rv64gcv"
try_march "rv64gcv_zba_zbb_zbs"
try_march "rv64gcv_zba_zbb_zbs_zbc"
try_march "rv64gcv_zba_zbb_zbs_zcb"
try_march "rva22u64"
try_march "rva23u64"
try_march "rva23u64_zvbb"

section "Relaxation / PLT flag acceptance"
try_march_with "rv64gc" "-mrelax"
try_march_with "rv64gc" "-mno-relax"
try_march_with "rv64gc" "-fno-plt"
try_march_with "rv64gc" "-mrelax -fno-plt"

section "Predefined __riscv_* macros per tier"
echo "What does the compiler think is enabled for each tier?"
for arch in rv64gc rv64gcv_zba_zbb_zbs rva23u64; do
    echo
    echo "-- $arch --"
    tmp="$(mktemp -d)"
    if "$GCC" -march="$arch" -mabi=lp64d -E -dM -x c /dev/null \
              > "$tmp/macros" 2> "$tmp/err"; then
        grep -E '^#define __riscv' "$tmp/macros" | sort | sed 's/^/  /'
    else
        echo "  (toolchain rejected this -march; skipped)"
        sed 's/^/    | /' < "$tmp/err" | head -n 4
    fi
    rm -rf "$tmp"
done

section "End of probe"
