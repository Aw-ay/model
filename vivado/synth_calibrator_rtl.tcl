if {[version -short] ne {2025.2}} {
    error {Vivado 2025.2 is required}
}
set source_dir [file normalize [file join [file dirname [info script]] ..]]
set build_dir [file join $source_dir build rtl_synth]
file mkdir $build_dir

set rtl_tops {calibrator_core calibrator_control_axi calibrator_control_cdc}
if {[info exists ::env(CALIBRATOR_RTL_TOPS)]} {
    set rtl_tops $::env(CALIBRATOR_RTL_TOPS)
}
foreach top $rtl_tops {
    create_project -in_memory -part xczu27dr-fsve1156-2-i
    read_verilog -sv [file join $source_dir rtl ${top}.sv]
    synth_design -top $top -part xczu27dr-fsve1156-2-i -mode out_of_context
    report_drc -file [file join $build_dir ${top}_drc.rpt]
    write_checkpoint -force [file join $build_dir ${top}.dcp]
    close_project
}

puts {CALIBRATOR_RTL_SYNTH_OK}
exit
