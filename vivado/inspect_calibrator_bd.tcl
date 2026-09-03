open_project [file normalize {build/calibrator_project/calibrator.xpr}]
open_bd_design [get_files */calibrator.bd]
puts {=== RFDC PINS ===}
current_bd_design calibrator
foreach pin [lsort [get_bd_pins -of_objects [get_bd_cells rfdc_0]]] {
  puts "[get_property NAME $pin] DIR=[get_property DIR $pin] TYPE=[get_property TYPE $pin]"
}
puts {=== RFDC INTERFACES ===}
foreach pin [lsort [get_bd_intf_pins -of_objects [get_bd_cells rfdc_0]]] {
  puts "[get_property NAME $pin] MODE=[get_property MODE $pin] VLNV=[get_property VLNV $pin]"
}
puts {=== PS INTERFACES ===}
foreach pin [lsort [get_bd_intf_pins -of_objects [get_bd_cells ps_0]]] {
  puts "[get_property NAME $pin] MODE=[get_property MODE $pin] VLNV=[get_property VLNV $pin]"
}
puts {=== RFDC CONFIG ===}
foreach prop [lsort [list_property [get_bd_cells rfdc_0]]] {
  if {[string match *Data_Width* $prop] || [string match *Fabric_Freq* $prop] || [string match *Samples_Per_Clock* $prop]} {
    puts "$prop=[get_property $prop [get_bd_cells rfdc_0]]"
  }
}
exit
