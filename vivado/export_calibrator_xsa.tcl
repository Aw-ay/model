if {[version -short] ne {2025.2}} { error {Vivado 2025.2 is required} }
set source_dir [file normalize [file join [file dirname [info script]] ..]]
set build_dir [file join $source_dir build calibrator_project]
open_project [file join $build_dir calibrator.xpr]
open_checkpoint [file join $build_dir post_route.dcp]
write_hw_platform -fixed -force -file [file join $build_dir calibrator_no_bit.xsa]
exit
