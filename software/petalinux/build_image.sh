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
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/src/protocol.c" \
    "$CALIBRATORD_RECIPE_FILES/protocol.c"
install -m 0644 "$REPOSITORY_ROOT/software/calibratord/include/calibrator_protocol.h" \
    "$CALIBRATORD_RECIPE_FILES/calibrator_protocol.h"
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
    petalinux-config --get-hw-description="$PROJECT_PATH/hardware" --silentconfig
    ROOTFS_CONFIG="$PROJECT_PATH/project-spec/configs/rootfs_config"
    while IFS= read -r setting; do
        [[ -z "$setting" ]] && continue
        grep -qxF "$setting" "$ROOTFS_CONFIG" || printf '%s\n' "$setting" >> "$ROOTFS_CONFIG"
    done < "$REPOSITORY_ROOT/petalinux/project-spec/configs/rootfs_config.fragment"
    petalinux-config -c rootfs --silentconfig
    petalinux-build
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
        --bootfiles "BOOT.BIN Image boot.scr"
)

echo "PetaLinux image: $PROJECT_PATH/images/linux/petalinux-sdimage.wic"
