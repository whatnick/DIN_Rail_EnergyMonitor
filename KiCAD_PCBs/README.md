# KiCAD PCB's for DIN rail Energy Monitor Design

This is a modular systems with usually 
 - x3 custom PCB's performing metering and energy sampling 
 - 1 or more off the shelf PCB's providing host cpu and display

The custom PCB's for a C-shaped assembly which sits in the DIN Rail. Possibly not the most 
efficient use of space, but it works for this design. In principal the x3 PCB's are:
 - **Power and voltage/current sampling PCB** - This design is fairly stable and should work with 
lots of metering and front-end options. Limitations are AC-voltage, DC-power requirements and
 minor tweaks on CT multiplier resistors depending on current clamp and limitations of the 
meterin IC used.
 - **Metering PCB** - The current options are dual-ATM90E26 and dual-ATM90E36, these add x2
single-phase or x2 three-phase metering capabilty.
 - **Isolator PCB** - This is the simplest PCB which provides SPI isolation to CPU module. It 
has plenty of room to be extended to include additional I2C sensors or microSD card etc. It can
 also be modified to adapt to different CPU's, on the Roadmap are ESP32, Onion and Raspberry Pi.
