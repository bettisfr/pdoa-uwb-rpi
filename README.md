# pdoa-uwb-rpi

Small Raspberry Pi 5 workspace for reading Decawave/Qorvo DWM1002 PDoA node reports over USB serial.

The current setup is:

- DWM1002 PDoA node connected to the Raspberry Pi 5 via `usb_module`;
- flashed DWM1001/DWM1003-style tags running the Decawave PDoA tag firmware;
- a C monitor that reads `/dev/ttyACM0` and shows one stable row per active tag.

## Build

```bash
make
```

## Run On Raspberry Pi

```bash
./pdoa-monitor -d /dev/ttyACM0
```

Default output is a stable dashboard:

```text
PDoA monitor - 3 active tags - 18:48:12
age      tag                 seq range_cm pdoa_deg    x_cm    y_cm  clk_ppm     t_us
0s       dw00                121       22     -120      20       9     1.69    32318
0s       dw01                197       45      -92      45       0     2.08    42327
0s       dw02                170       24      -98      24       0     2.26    52368
```

Use stream mode for raw logging/debugging:

```bash
./pdoa-monitor -d /dev/ttyACM0 --stream
```

Every run writes a CSV log under `logs/`:

```text
logs/pdoa_YYYYMMDD_HHMMSS.csv
```

CSV columns:

```text
time,tag,a16,seq,range_cm,pdoa_deg,x_cm,y_cm,clk_ppm,t_us
```

## Web UI

Run the simple web frontend on the Raspberry Pi:

```bash
make web
```

It starts `./pdoa-monitor`, writes continuous CSV logs, and serves a
mobile-first field interface at:

```text
http://<raspberry-pi-ip>:8080
```

The light, high-contrast interface is designed for phones and tablets. It
provides:

- editable experiment name, node height, and sample target before acquisition;
- separate DWM1002 node and nine-tag readiness checks;
- the planned bearing on every tag status tile;
- distance and relative tag rotation selection;
- automatic completion when every tag reaches the sample target;
- amber partial acquisition when one or more tags are unavailable;
- persistent progress across all 60 distance and rotation combinations;
- live range, PDoA, and sample age details.

The monitor retries the serial connection every five seconds, so reconnecting
the DWM1002 does not require restarting the web server.

Default URL in the current setup:

```text
http://192.168.1.67:8080
```

Experiment setup can be edited until the first run starts. Once acquisition has
begun, it is locked to keep run metadata consistent.

Experiment data is stored separately from the continuous monitor log:

```text
datasets/<experiment-id>/
  experiment.json
  runs/
    d002m_r000_run01.csv
```

Run files include the node height, target distance, relative tag rotation,
planned tag bearing, expected tags, participating tags, missing tags, and all raw
monitor fields. Samples with `(x_cm, y_cm)` equal to `(0, 0)` remain in the CSV
but do not count toward run completion.

With all nine tags ready, the interface starts a complete run. With fewer tags,
an amber action asks for confirmation and records a partial run. Completion is
based only on the tags present at run start. A 120-second timeout prevents a tag
failure during acquisition from blocking the run indefinitely. Partial
conditions remain available for a later recovery run.

Both `logs/` and `datasets/` are excluded from Git and Raspberry Pi sync
deletion. Field data therefore remains on the Raspberry Pi across deployments.

## Tag Config

Tag labels are loaded from `config/tags.json`.

Current tags:

```json
{
  "tags": [
    {
      "a16": "8103",
      "id": "013A6102C3F58103",
      "name": "dw00"
    },
    {
      "a16": "1729",
      "id": "013A6102C4351729",
      "name": "dw01"
    },
    {
      "a16": "8FB0",
      "id": "013A6102C3F48FB0",
      "name": "dw02"
    },
    {
      "a16": "021B",
      "id": "013A6102C435021B",
      "name": "dw03"
    },
    {
      "a16": "0F85",
      "id": "013A6102C3F50F85",
      "name": "dw04"
    },
    {
      "a16": "4B92",
      "id": "013A6102C3F44B92",
      "name": "dw05"
    },
    {
      "a16": "0789",
      "id": "013A6102C3F40789",
      "name": "dw06"
    },
    {
      "a16": "5783",
      "id": "013A6102C3F55783",
      "name": "dw07"
    },
    {
      "a16": "028E",
      "id": "013A6102C435028E",
      "name": "dw08"
    }
  ]
}
```

`a16` is the short address configured on the DWM1002 node. `id` is the tag long address reported by the node. `name` is what the monitor displays.

## Measurement Layout

Place the DWM1002 node at the logical origin `(0, 0)`. Arrange the nine tags at
fixed bearings around the 90-degree center line:

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

Run measurements at radial distances from 2 m through 30 m, in 2 m steps:

```text
2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30 m
```

Keep all tags at the same height and antenna orientation for each measurement.

To evaluate whether tag reception is isotropic, repeat each position and distance
measurement with four relative tag rotations around the vertical axis:

```text
0, 90, 180, 270 deg
```

Use the same physical face as the 0-degree reference for every tag. Change only
the tag rotation while keeping its position, height, and the node orientation
fixed.

For the full measurement campaign, repeat the experiment with the DWM1002 node
at three heights above the reference ground plane:

```text
0, 2, 4 m
```

Keep the tag layout and the node's horizontal position at `(0, 0)` unchanged
when changing the node height.

## Sync To Raspberry Pi

The Raspberry Pi clone is expected at `/home/fra/pdoa-uwb-rpi`.

```bash
./scripts/sync-rpi.sh
```

Sync, build, and restart the web monitor:

```bash
./scripts/sync-rpi.sh --web
```

Useful web options:

```bash
./scripts/sync-rpi.sh --web --web-port 8080 --web-device /dev/ttyACM0 --stddev-window 100
```

Defaults:

```bash
RPI_HOST=fra@192.168.1.67
RPI_DIR=/home/fra/pdoa-uwb-rpi
```

Override them if needed:

```bash
RPI_HOST=fra@raspberrypi.local RPI_DIR=/home/fra/pdoa-uwb-rpi ./scripts/sync-rpi.sh
```

## Flashing Tags

The tag firmware used during setup is:

```text
/mnt/data/altro/antenne/_beta/Software/ARM_Hex/dwm1003_tag/dw_pdoa_tag.hex
```

Flash with SEGGER J-Link:

```bash
JLinkExe -device nRF52832_xxAA -if SWD -speed 4000 -autoconnect 1
```

Then in J-Link Commander:

```text
halt
erase
loadfile /mnt/data/altro/antenne/_beta/Software/ARM_Hex/dwm1003_tag/dw_pdoa_tag.hex
r
g
q
```

After flashing, the DWM1002 reports the tag as `NewTag`. Add it to the node KList with:

```text
ADDTAG <long_id> <short_id> 2 64 0
SAVE
```

## Report Fields

The DWM1002 JSON `TWR` report includes:

- `D`: range in centimeters;
- `P`: raw PDoA value, shown as `pdoa_deg`;
- `Xcm`, `Ycm`: node-estimated tag coordinates in centimeters;
- `O`: clock offset in hundredths of ppm, shown as `clk_ppm = O / 100`;
- `T`: timestamp inside the node superframe in microseconds, shown as `t_us`;
- `X`, `Y`, `Z`: tag accelerometer values in mg.

The firmware does not output a separate geometric bearing field. The web UI derives `bearing_deg` from `Xcm` and `Ycm`.
