#!/usr/bin/env bash
set -euo pipefail

REQUIRED_VERSION="2025.2"

if [[ $# -ne 2 ]]; then
    echo "usage: build_image.sh <calibrator.xsa> <new-project-directory>" >&2
    exit 2
fi

XSA_PATH="$(realpath "$1")"
PROJECT_PATH="$(realpath -m "$2")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(realpath "$SCRIPT_DIR/../..")"

if [[ ! -f "$XSA_PATH" ]]; then
    echo "XSA not found: $XSA_PATH" >&2
    exit 2
fi
if [[ -e "$PROJECT_PATH" ]]; then
    echo "refusing to overwrite existing path: $PROJECT_PATH" >&2
    exit 2
fi
for command in python3 sha256sum; do
    command -v "$command" >/dev/null || { echo "missing $command" >&2; exit 2; }
done
XSA_MANIFEST="$REPOSITORY_ROOT/docs/deployment/petalinux-2025.2-artifacts.json"
if [[ ! -f "$XSA_MANIFEST" ]]; then
    echo "qualified artifact manifest not found: $XSA_MANIFEST" >&2
    exit 2
fi
EXPECTED_XSA_SHA256="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["vivado"]["xsa"]["sha256"])' "$XSA_MANIFEST")"
ACTUAL_XSA_SHA256="$(sha256sum "$XSA_PATH" | awk '{print $1}')"
if [[ ! "$EXPECTED_XSA_SHA256" =~ ^[0-9a-f]{64}$ || "$ACTUAL_XSA_SHA256" != "$EXPECTED_XSA_SHA256" ]]; then
    echo "XSA digest does not match the qualified Vivado artifact" >&2
    echo "expected: $EXPECTED_XSA_SHA256" >&2
    echo "actual:   $ACTUAL_XSA_SHA256" >&2
    exit 2
fi
if [[ "${PETALINUX:-}" != *"$REQUIRED_VERSION"* ]]; then
    echo "source the PetaLinux $REQUIRED_VERSION settings.sh before running this script" >&2
    exit 2
fi
if ! grep -q '^VERSION_ID="22.04' /etc/os-release; then
    echo "Ubuntu 22.04 is required for this qualified build" >&2
    exit 2
fi
for command in petalinux-create petalinux-config petalinux-build petalinux-package; do
    command -v "$command" >/dev/null || { echo "missing $command" >&2; exit 2; }
done

XSCT_LIBTINFO_DIR="${CALIBRATOR_XSCT_LIBTINFO_DIR:-}"
if [[ -z "$XSCT_LIBTINFO_DIR" ]]; then
    XSCT_LIBTINFO_FILE="$(ldconfig -p 2>/dev/null | awk '/libtinfo\.so\.5 / {print $NF; exit}')"
    XSCT_LIBTINFO_DIR="${XSCT_LIBTINFO_FILE%/*}"
fi
if [[ -z "$XSCT_LIBTINFO_DIR" || ! -f "$XSCT_LIBTINFO_DIR/libtinfo.so.5" ]]; then
    echo "PetaLinux XSCT requires libtinfo.so.5; set CALIBRATOR_XSCT_LIBTINFO_DIR to its directory" >&2
    exit 2
fi
XSCT_LIBTINFO_DIR="$(realpath "$XSCT_LIBTINFO_DIR")"

run_petalinux() {
    env -u LD_PRELOAD \
        LIBRARY_PATH="$XSCT_LIBTINFO_DIR" \
        BB_ENV_PASSTHROUGH_ADDITIONS="${BB_ENV_PASSTHROUGH_ADDITIONS:-} LIBRARY_PATH" \
        "$@"
}

# gen-machineconf launches XSCT before BitBake's recipe-scoped environment
# exists. Preload libtinfo only for this command; ordinary Linux tasks keep
# using the clean launcher above.
run_petalinux_xsct() {
    env LD_PRELOAD="$XSCT_LIBTINFO_DIR/libtinfo.so.5" \
        LIBRARY_PATH="$XSCT_LIBTINFO_DIR" \
        BB_ENV_PASSTHROUGH_ADDITIONS="${BB_ENV_PASSTHROUGH_ADDITIONS:-} LIBRARY_PATH" \
        "$@"
}

PROJECT_PARENT="$(dirname "$PROJECT_PATH")"
PROJECT_NAME="$(basename "$PROJECT_PATH")"
mkdir -p "$PROJECT_PARENT"
(
    cd "$PROJECT_PARENT"
    petalinux-create -t project --template zynqMP -n "$PROJECT_NAME"
)

mkdir -p "$PROJECT_PATH/hardware"
install -m 0644 "$XSA_PATH" "$PROJECT_PATH/hardware/calibrator.xsa"
cp -a "$REPOSITORY_ROOT/petalinux/project-spec/meta-user/." \
      "$PROJECT_PATH/project-spec/meta-user/"

CALIBRATORD_RECIPE_FILES="$PROJECT_PATH/project-spec/meta-user/recipes-apps/calibratord/files"
DMA_PROXY_RECIPE_FILES="$PROJECT_PATH/project-spec/meta-user/recipes-apps/calibrator-dma-proxy/files"
mkdir -p "$CALIBRATORD_RECIPE_FILES" "$DMA_PROXY_RECIPE_FILES"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/src/calibratord.c" \
    "$CALIBRATORD_RECIPE_FILES/calibratord.c"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/src/control.c" \
    "$CALIBRATORD_RECIPE_FILES/control.c"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/src/protocol.c" \
    "$CALIBRATORD_RECIPE_FILES/protocol.c"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/include/calibrator_protocol.h" \
    "$CALIBRATORD_RECIPE_FILES/calibrator_protocol.h"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/include/calibrator_control.h" \
    "$CALIBRATORD_RECIPE_FILES/calibrator_control.h"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/include/calibrator_regs.h" \
    "$CALIBRATORD_RECIPE_FILES/calibrator_regs.h"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/include/calibrator_uio_path.h" \
    "$CALIBRATORD_RECIPE_FILES/calibrator_uio_path.h"
install -m 0644 "$REPOSITORY_ROOT/software/kernel/calibrator_dma_proxy.c" \
    "$DMA_PROXY_RECIPE_FILES/calibrator_dma_proxy.c"
install -m 0644 "$REPOSITORY_ROOT/software/kernel/Makefile" \
    "$DMA_PROXY_RECIPE_FILES/Makefile"

(
    cd "$PROJECT_PATH"
    run_petalinux_xsct petalinux-config --get-hw-description="$PROJECT_PATH/hardware" --silentconfig
    cat >> "$PROJECT_PATH/build/conf/local.conf" <<EOF

# Scope the host libtinfo.so.5 compatibility library to recipes that invoke XSCT.
LD_PRELOAD = ""
LIBRARY_PATH = ""
LD_PRELOAD:pn-device-tree = "$XSCT_LIBTINFO_DIR/libtinfo.so.5"
LIBRARY_PATH:pn-device-tree = "$XSCT_LIBTINFO_DIR"
LD_PRELOAD:pn-bitstream-extraction = "$XSCT_LIBTINFO_DIR/libtinfo.so.5"
LIBRARY_PATH:pn-bitstream-extraction = "$XSCT_LIBTINFO_DIR"
LD_PRELOAD:pn-pmu-firmware = "$XSCT_LIBTINFO_DIR/libtinfo.so.5"
LIBRARY_PATH:pn-pmu-firmware = "$XSCT_LIBTINFO_DIR"
LD_PRELOAD:pn-fsbl-firmware = "$XSCT_LIBTINFO_DIR/libtinfo.so.5"
LIBRARY_PATH:pn-fsbl-firmware = "$XSCT_LIBTINFO_DIR"
LD_PRELOAD[export] = "1"
LIBRARY_PATH[export] = "1"
EOF
    ROOTFS_CONFIG="$PROJECT_PATH/project-spec/configs/rootfs_config"
    while IFS= read -r setting; do
        [[ -z "$setting" ]] && continue
        grep -qxF "$setting" "$ROOTFS_CONFIG" || printf '%s\n' "$setting" >> "$ROOTFS_CONFIG"
    done < "$REPOSITORY_ROOT/petalinux/project-spec/configs/rootfs_config.fragment"
    run_petalinux petalinux-config -c rootfs --silentconfig
    run_petalinux petalinux-build
    python3 "$REPOSITORY_ROOT/software/petalinux/extract_xsa_bitstream.py" \
        "$PROJECT_PATH/hardware/calibrator.xsa" images/linux/system.bit
    petalinux-package --boot \
        --fsbl images/linux/zynqmp_fsbl.elf \
        --fpga images/linux/system.bit \
        --pmufw images/linux/pmufw.elf \
        --atf images/linux/bl31.elf \
        --u-boot images/linux/u-boot.elf \
        --force
    petalinux-package --wic \
        --images-dir images/linux \
        --bootfiles "BOOT.BIN Image boot.scr system.dtb"
)

echo "PetaLinux image: $PROJECT_PATH/images/linux/petalinux-sdimage.wic"
