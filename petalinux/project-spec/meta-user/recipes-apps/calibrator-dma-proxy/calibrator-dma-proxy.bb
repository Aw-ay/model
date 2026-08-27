SUMMARY = "RFSoC calibrator DMA proxy kernel module"
LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI = "file://calibrator_dma_proxy.c \
           file://Makefile"

S = "${WORKDIR}"
DEPENDS += "virtual/kernel"

inherit module

KERNEL_MODULE_AUTOLOAD += "calibrator_dma_proxy"
