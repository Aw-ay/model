proc calibrator_main {arguments} {
    if {[llength $arguments] != 2} {
        error "usage: create_linux_platform.tcl <calibrator.xsa> <output-directory>"
    }

    set xsa [file normalize [lindex $arguments 0]]
    set output_dir [file normalize [lindex $arguments 1]]
    if {![info exists ::env(XILINX_VITIS)]} {
        error "XILINX_VITIS is not set"
    }
    set vitis_root [string map {\\ /} $::env(XILINX_VITIS)]
    if {[string first "2025.2" $vitis_root] < 0} {
        error "Vitis 2025.2 required; XILINX_VITIS=$vitis_root"
    }
    set qemu_payload [file join $vitis_root data emulation platforms zynqmp sw a53_linux qemu]
    if {![file isdirectory $qemu_payload]} {
        error "Vitis Embedded ZynqMP Linux payload is incomplete: $qemu_payload"
    }
    if {![file isfile $xsa]} {
        error "XSA does not exist: $xsa"
    }
    if {[file exists $output_dir]} {
        error "refusing to reuse existing output directory: $output_dir"
    }

    file mkdir $output_dir
    platform create -name calibrator_platform -hw $xsa -out $output_dir -no-boot-bsp
    domain create -name linux_a53 -os linux -proc psu_cortexa53 -arch 64-bit
    puts [platform report]
    platform generate

    set xpfm [file join $output_dir calibrator_platform export calibrator_platform calibrator_platform.xpfm]
    if {![file isfile $xpfm]} {
        error "XSCT did not create the expected XPFM: $xpfm"
    }
    puts "CALIBRATOR_XPFM=[string map {\\ /} $xpfm]"
}

if {[catch {calibrator_main $argv} message options]} {
    puts stderr "ERROR: $message"
    if {[dict exists $options -errorinfo]} {
        puts stderr [dict get $options -errorinfo]
    }
    exit 1
}
exit 0
