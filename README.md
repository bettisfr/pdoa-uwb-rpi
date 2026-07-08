# pdoa-uwb-rpi

Experimental repository for working with Decawave/Qorvo UWB modules on Raspberry Pi 5, with a focus on PDoA (Phase Difference of Arrival) measurements and angle-of-arrival estimation.

## Goal

The project aims to build a practical base for:

- driving one or more Decawave/Qorvo UWB transceivers from a Raspberry Pi 5;
- collecting raw measurements for ranging, TDoA/PDoA, and radio debugging;
- experimenting with antenna calibration and phase offsets;
- estimating the direction/angle of arrival of a UWB tag;
- keeping hardware access, measurement logic, and analysis tools clearly separated.

This repository starts as a lab workspace: first reliable wiring and low-level reads, then algorithms and visualization.

## Target Hardware

Expected setup, to be confirmed during development:

- Raspberry Pi 5;
- SPI-compatible Decawave/Qorvo UWB module;
- one or more UWB antennas for PDoA experiments;
- stable 3.3 V power supply;
- SPI plus GPIO wiring for reset, interrupt, and chip select.

Possible chip/module families:

- DW1000 / DWM1000;
- DW3000 / DWM3000;
- newer Qorvo modules compatible with phase measurements.

## Planned Structure

```text
.
├── README.md
├── docs/              # hardware notes, wiring, calibration
├── src/               # drivers and application logic
├── tools/             # acquisition, logging, and analysis scripts
├── data/              # local samples, ignored or versioned deliberately
└── tests/             # unit tests and simulations
```

## Initial Plan

1. Document the selected UWB module and Raspberry Pi 5 pinout.
2. Enable SPI on Raspberry Pi OS and verify basic communication.
3. Read chip identification registers.
4. Implement a first packet/ranging acquisition path.
5. Store reproducible logs in CSV/JSONL.
6. Add phase/antenna calibration routines.
7. Implement a first PDoA/AoA estimate.
8. Add lightweight visualization or a real-time debug dashboard.

## Raspberry Pi 5 Notes

Before connecting hardware:

- verify that the module uses 3.3 V logic and does not need level shifting;
- check current draw and power stability;
- enable SPI with `raspi-config` or an equivalent configuration method;
- assign dedicated pins for `CS`, `RST`, and `IRQ`;
- keep SPI wires short during the first tests.

Example SPI bus check:

```bash
ls /dev/spidev*
```

## Status

Initial phase. The repository currently contains starter documentation; drivers, tools, and tests will be added once the exact UWB module is selected.

## TODO

- [ ] choose the reference UWB chip/module;
- [ ] add Raspberry Pi 5 wiring diagram;
- [ ] define the main language/runtime;
- [ ] create the first SPI probe script;
- [ ] document the log format;
- [ ] collect first test datasets;
- [ ] implement PDoA calibration;
- [ ] validate angular estimation with a known setup.

## License

To be defined.
