SUMMARY = "RFSoC calibrator control, RFDC/MTS and UDP event service"
LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI = "file://calibratord.c \
           file://protocol.c \
           file://calibrator_protocol.h \
           file://calibrator_regs.h \
           file://calibrator_dma_proxy.c \
           file://Makefile \
           file://calibratord.service \
           file://calibratord.default"

S = "${WORKDIR}"
DEPENDS = "libmetal libxrfdc virtual/kernel"

inherit module systemd

SYSTEMD_SERVICE:${PN} = "calibratord.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"
KERNEL_MODULE_AUTOLOAD += "calibrator_dma_proxy"

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -I${S} -o calibratord \
        calibratord.c protocol.c -pthread -lmetal -lxrfdc
    oe_runmake -C ${STAGING_KERNEL_DIR} M=${S} modules
}

do_install() {
    install -d ${D}${sbindir} ${D}${systemd_system_unitdir} ${D}${sysconfdir}/default
    install -m 0755 calibratord ${D}${sbindir}/calibratord
    install -m 0644 ${WORKDIR}/calibratord.service ${D}${systemd_system_unitdir}/calibratord.service
    install -m 0644 ${WORKDIR}/calibratord.default ${D}${sysconfdir}/default/calibratord
    module_do_install
}

FILES:${PN} += "${systemd_system_unitdir}/calibratord.service ${sysconfdir}/default/calibratord"
RDEPENDS:${PN} += "libmetal libxrfdc kernel-module-uio-pdrv-genirq"
