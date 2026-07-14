# pdoa-uwb-rpi

Raspberry Pi 5 acquisition stack for a Decawave/Qorvo DWM1002 PDoA node and
multiple DWM1001/DWM1003-compatible tags.

The DWM1002 is connected through `usb_module` and appears as `/dev/ttyACM0`.
The repository provides:

- `pdoa-monitor`, a C serial reader with a stable terminal dashboard and CSV logging;
- a mobile-first field interface for guided experiments;
- persistent experiment state and per-run CSV datasets;
- a `systemd` service for unattended acquisition.

## Deployed System

The current deployment uses:

| Item | Value |
| --- | --- |
| Raspberry Pi | `rpi5-01.local` |
| SSH user | `fra` |
| Service user and group | `rpi:rpi` |
| Repository | `/opt/pdoa-uwb-rpi` |
| Shared Python environment | `/opt/pyenv` |
| DWM1002 serial device | `/dev/ttyACM0` |
| Web service | `pdoa-web.service` |
| Web URL | `http://rpi5-01.local:8080` |

The `rpi` account has no interactive login and belongs to `dialout`. Human
administrators belong to the `rpi` group and use their own SSH accounts and
keys. The checkout and Python environment therefore do not depend on a human
home directory.

Connect to the deployed Pi with:

```bash
ssh fra@rpi5-01.local
```

## Hardware Check

The DWM1002 is expected to identify as Nordic Semiconductor `1915:520f`:

```bash
lsusb
ls -l /dev/ttyACM0
```

Expected device permissions:

```text
crw-rw---- root dialout /dev/ttyACM0
```

The web server remains available if the node is disconnected. The monitor
retries the serial connection every five seconds and resumes acquisition when
`/dev/ttyACM0` returns.

## Build And Terminal Monitor

Build on the Raspberry Pi:

```bash
cd /opt/pdoa-uwb-rpi
sudo -u rpi make
```

Stop the web service before opening the serial device manually:

```bash
sudo systemctl stop pdoa-web
sudo -u rpi ./pdoa-monitor -d /dev/ttyACM0
```

The default view redraws one stable row per active tag:

```text
age      tag  seq range_cm pdoa_deg x_cm y_cm clk_ppm    t_us
0s       dw07 183       66       20  -28   60   -3.69 2147483
```

Use stream mode for serial debugging:

```bash
sudo -u rpi ./pdoa-monitor -d /dev/ttyACM0 --stream
```

Restart normal unattended acquisition afterward:

```bash
sudo systemctl start pdoa-web
```

Every monitor execution writes a timestamped CSV:

```text
logs/pdoa_YYYYMMDD_HHMMSS.csv
```

Raw CSV columns are:

```text
time,tag,a16,seq,range_cm,pdoa_deg,x_cm,y_cm,clk_ppm,t_us
```

## System Service

Install the unit after provisioning or changing `systemd/pdoa-web.service`:

```bash
cd /opt/pdoa-uwb-rpi
./scripts/install-service.sh
```

The installer copies the unit to `/etc/systemd/system`, reloads `systemd`, and
enables and starts the service. Normal operations use:

```bash
sudo systemctl start pdoa-web
sudo systemctl stop pdoa-web
sudo systemctl restart pdoa-web
systemctl status pdoa-web
systemctl is-enabled pdoa-web
systemctl is-active pdoa-web
journalctl -u pdoa-web -f
```

The service starts at boot, runs as the unprivileged `rpi` user, and restarts
after unexpected failures. `systemd` owns both the Python server and its
`pdoa-monitor` child, so manual background processes are not required.

## Web Interface

Open the field interface from a phone, tablet, or computer on the same network:

```text
http://rpi5-01.local:8080
```

If mDNS is unavailable, find the current address and use the IP instead:

```bash
nmap -sn 192.168.1.0/24
```

The interface provides:

- editable dataset name, node height, and sample target before acquisition;
- independent node and nine-tag readiness checks;
- planned bearing on each tag tile;
- distance and relative tag rotation selection;
- automatic completion when participating tags reach the target;
- confirmed partial runs when one or more tags are unavailable;
- persistent progress for all distance and rotation conditions;
- per-bearing count, mean range, range standard deviation, and circular mean PDoA.

Experiment setup is locked after the first run to keep metadata consistent. A
run times out after 120 seconds, and partial conditions can be repeated later.
Samples where `(x_cm, y_cm) == (0, 0)` remain in raw CSV files but do not count
toward run completion or aggregate statistics.

## Stored Data

Continuous monitor files remain under `logs/`. Guided experiments use:

```text
datasets/<experiment-id>/
  experiment.json
  runs/
    d002m_r000_run01.csv
```

Run files record node height, target distance, relative tag rotation, planned
bearing, expected tags, participating tags, missing tags, and raw monitor
fields. Both `logs/` and `datasets/` are ignored by Git and excluded from sync
deletion.

Reset all saved runs for the current experiment with the API-only operation:

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"confirm":"DELETE_ALL_RUNS"}' \
  http://rpi5-01.local:8080/api/runs/clear
```

This preserves the experiment configuration and continuous monitor logs.

## Tag Configuration

Aliases are defined in `config/tags.json`:

| Name | Short address | Long address |
| --- | --- | --- |
| `dw00` | `8103` | `013A6102C3F58103` |
| `dw01` | `1729` | `013A6102C4351729` |
| `dw02` | `8FB0` | `013A6102C3F48FB0` |
| `dw03` | `021B` | `013A6102C435021B` |
| `dw04` | `0F85` | `013A6102C3F50F85` |
| `dw05` | `4B92` | `013A6102C3F44B92` |
| `dw06` | `0789` | `013A6102C3F40789` |
| `dw07` | `5783` | `013A6102C3F55783` |
| `dw08` | `028E` | `013A6102C435028E` |

The short address is configured in the DWM1002 KList. The long address is
reported by the node, and the name is used by the monitor and web interface.

## Measurement Campaign

Place the DWM1002 at logical origin `(0, 0)` and arrange tags around the
90-degree center line:

| Tag | Bearing |
| --- | ---: |
| `dw00` | 15 deg |
| `dw01` | 35 deg |
| `dw02` | 55 deg |
| `dw03` | 75 deg |
| `dw04` | 90 deg |
| `dw05` | 105 deg |
| `dw06` | 125 deg |
| `dw07` | 145 deg |
| `dw08` | 165 deg |

Measure at `2, 4, ..., 30 m`, with relative tag rotations `0, 90, 180, 270
deg` and relative node heights `0, 2, 4 m`. Height `0 m` means the node and
tags share the same reference height; it does not require placing hardware on
the ground.

For radial distance `r`, place `dw04` on the center line and locate symmetric
tag pairs using their chord distance from `dw04`:

```text
c = 2 * r * sin_deg(abs(bearing_deg - 90) / 2)
```

| Tags | Bearings | Chord from `dw04` |
| --- | ---: | ---: |
| `dw03`, `dw05` | 75, 105 deg | `0.2611 * r` |
| `dw02`, `dw06` | 55, 125 deg | `0.6014 * r` |
| `dw01`, `dw07` | 35, 145 deg | `0.9235 * r` |
| `dw00`, `dw08` | 15, 165 deg | `1.2175 * r` |

The full campaign contains 180 runs:

```text
15 distances * 4 rotations * 3 node heights = 180 runs
180 runs * 9 tags * 200 valid samples = 324,000 valid measurements
```

## Deployment From A Workstation

Sync the local working tree, compile remotely, and optionally restart the
service:

```bash
./scripts/sync-rpi.sh
./scripts/sync-rpi.sh --web
```

Defaults are:

```text
RPI_HOST=fra@rpi5-01.local
RPI_DIR=/opt/pdoa-uwb-rpi
```

Override them for another provisioned Pi:

```bash
RPI_HOST=fra@rpi5-02.local ./scripts/sync-rpi.sh --web
```

The sync excludes `.git`, generated binaries, caches, `logs/`, and `datasets/`.

## Flashing Tags

The firmware used for the configured tags is:

```text
/mnt/data/altro/antenne/_beta/Software/ARM_Hex/dwm1003_tag/dw_pdoa_tag.hex
```

Start SEGGER J-Link Commander on Linux:

```bash
JLinkExe -device nRF52832_xxAA -if SWD -speed 4000 -autoconnect 1
```

Then run:

```text
halt
erase
loadfile /mnt/data/altro/antenne/_beta/Software/ARM_Hex/dwm1003_tag/dw_pdoa_tag.hex
r
g
q
```

Add a newly reported tag to the DWM1002 KList and persist it:

```text
ADDTAG <long_id> <short_id> 2 64 0
SAVE
```

## Report Fields

The DWM1002 `TWR` JSON includes:

- `D`: range in centimeters, displayed as `range_cm`;
- `P`: raw PDoA value, displayed as `pdoa_deg`;
- `Xcm`, `Ycm`: node-estimated coordinates in centimeters;
- `O`: clock offset in hundredths of ppm, displayed as `clk_ppm = O / 100`;
- `T`: node superframe timestamp in microseconds, displayed as `t_us`;
- `X`, `Y`, `Z`: tag accelerometer values in mg.

The firmware does not report a separate geometric bearing. Any geometric
bearing is derived from `Xcm` and `Ycm`; planned tag bearing is experiment
metadata and must not be confused with raw PDoA.
