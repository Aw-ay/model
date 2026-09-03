if {[version -short] ne {2025.2}} {
    error {Vivado 2025.2 is required}
}

create_project -in_memory -part xczu27dr-fsve1156-2-i

foreach required_ip {
    xilinx.com:ip:usp_rf_data_converter:2.6
    xilinx.com:ip:zynq_ultra_ps_e:3.5
    xilinx.com:ip:axi_dma:7.1
    xilinx.com:ip:axis_combiner:1.1
    xilinx.com:ip:axis_subset_converter:1.1
    xilinx.com:ip:axis_register_slice:1.1
    xilinx.com:ip:axis_broadcaster:1.1
} {
    if {[llength [get_ipdefs -all -quiet $required_ip]] != 1} {
        error "required IP is unavailable or ambiguous: $required_ip"
    }
}

puts {CALIBRATOR_VIVADO_SMOKE_OK}
close_project
exit
