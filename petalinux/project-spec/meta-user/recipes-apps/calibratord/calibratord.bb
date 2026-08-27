SUMMARY = "RFSoC calibrator control, RFDC/MTS and UDP event service"
LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI = "file://calibratord.c \
           file://control.c \
           file://protocol.c \
           file://calibrator_control.h \
           file://calibrator_protocol.h \
           file://calibrator_regs.h \
           file://calibrator_uio_path.h \
           file://calibratord.service \
           file://calibratord.default \
           file://calibrator-uio-modules.conf \
           file://uio-pdrv-genirq.conf"

S = "${WORKDIR}"
DEPENDS = "libmetal librfdc"

inherit systemd

SYSTEMD_SERVICE:${PN} = "calibratord.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -I${S} -o calibratord \
        calibratord.c control.c protocol.c -pthread -lmetal -lrfdc
}

do_install() {
    install -d ${D}${sbindir} ${D}${systemd_system_unitdir} ${D}${sysconfdir}/default \
        ${D}${sysconfdir}/modules-load.d ${D}${sysconfdir}/modprobe.d
    install -m 0755 calibratord ${D}${sbindir}/calibratord
    install -m 0644 ${WORKDIR}/calibratord.service ${D}${systemd_system_unitdir}/calibratord.service
    install -m 0644 ${WORKDIR}/calibratord.default ${D}${sysconfdir}/default/calibratord
    install -m 0644 ${WORKDIR}/calibrator-uio-modules.conf ${D}${sysconfdir}/modules-load.d/calibrator-uio.conf
    install -m 0644 ${WORKDIR}/uio-pdrv-genirq.conf ${D}${sysconfdir}/modprobe.d/uio-pdrv-genirq.conf
}

FILES:${PN} += "${sbindir}/calibratord ${systemd_system_unitdir}/calibratord.service \
    ${sysconfdir}/default/calibratord ${sysconfdir}/modules-load.d/calibrator-uio.conf \
    ${sysconfdir}/modprobe.d/uio-pdrv-genirq.conf"
RDEPENDS:${PN} += "libmetal librfdc kernel-module-calibrator-dma-proxy kernel-module-uio-pdrv-genirq"
