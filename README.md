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

It starts `./pdoa-monitor`, writes CSV logs, and serves a dashboard at:

```text
http://<raspberry-pi-ip>:8080
```

The page shows the latest tag rows plus a simple 2D plot with the node at `(0,0)` and tags placed from the reported `x_cm` and `y_cm` values.

The `range_avg_cm` and `range_std_cm` columns are computed by the web server from the latest `range_cm` samples in the current CSV log. They are not native DWM1002 fields.

The web API ignores samples where both `x_cm` and `y_cm` are zero, treating them as invalid position reports.

The `bearing_deg` column is derived from `atan2(y_cm, x_cm)`. It is the geometric bearing from the node origin, not the native PDoA value.

Default URL in the current setup:

```text
http://192.168.1.67:8080
```

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
    }
  ]
}
```

`a16` is the short address configured on the DWM1002 node. `id` is the tag long address reported by the node. `name` is what the monitor displays.

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
