#!/usr/bin/env python3
import argparse
from collections import defaultdict, deque
import csv
import json
import math
import os
import signal
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDoA Monitor</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }
    body { margin: 0; background: #101418; color: #e8eef5; }
    header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid #2a333d; }
    h1 { font-size: 20px; margin: 0; font-weight: 650; }
    main { padding: 18px 20px; }
    .plot-wrap { height: min(58vh, 560px); min-height: 320px; border: 1px solid #26313b; background: #0b0f13; margin-bottom: 18px; }
    svg { width: 100%; height: 100%; display: block; }
    .axis { stroke: #33404d; stroke-width: 1; }
    .grid { stroke: #202a33; stroke-width: 1; }
    .node { fill: #f0c85a; stroke: #ffe29a; stroke-width: 2; }
    .tag-dot { fill: #63b3ff; stroke: #b9dcff; stroke-width: 2; }
    .tag-label { fill: #e8eef5; font-size: 13px; font-weight: 650; }
    .tag-range { fill: #9fb0c2; font-size: 11px; }
    button { background: #2d6cdf; color: white; border: 0; border-radius: 6px; padding: 9px 14px; font-weight: 650; cursor: pointer; }
    button.secondary { background: #33404d; }
    .status { color: #9fb0c2; font-size: 14px; }
    table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
    th, td { text-align: right; padding: 10px 9px; border-bottom: 1px solid #26313b; }
    th:first-child, td:first-child { text-align: left; }
    tr.stale { color: #7f8b97; }
    .toolbar { display: flex; gap: 10px; align-items: center; }
    .empty { color: #9fb0c2; padding: 30px 0; }
  </style>
</head>
<body>
  <header>
    <h1>PDoA Monitor</h1>
    <div class="toolbar">
      <span id="status" class="status">Connecting...</span>
      <button id="start">Start</button>
      <button id="stop" class="secondary">Stop</button>
    </div>
  </header>
  <main>
    <div class="plot-wrap">
      <svg id="plot" viewBox="0 0 800 520" role="img" aria-label="relative tag positions"></svg>
    </div>
    <table>
      <thead>
        <tr>
          <th>tag</th>
          <th>age</th>
          <th>seq</th>
          <th>range_cm</th>
          <th>range_avg_cm</th>
          <th>range_std_cm</th>
          <th>pdoa_deg</th>
          <th>bearing_deg</th>
          <th>x_cm</th>
          <th>y_cm</th>
          <th>clk_ppm</th>
          <th>t_us</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
    <div id="empty" class="empty">No samples yet.</div>
  </main>
  <script>
    const rows = document.getElementById('rows');
    const empty = document.getElementById('empty');
    const statusEl = document.getElementById('status');
    const plot = document.getElementById('plot');

    async function post(path) {
      await fetch(path, {method: 'POST'});
      await refresh();
    }

    document.getElementById('start').onclick = () => post('/api/start');
    document.getElementById('stop').onclick = () => post('/api/stop');

    function cell(text) {
      const td = document.createElement('td');
      td.textContent = text;
      return td;
    }

    function svgEl(name, attrs = {}) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', name);
      for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
      return el;
    }

    function drawPlot(tags) {
      const width = 800;
      const height = 520;
      const cx = width / 2;
      const cy = height * 0.72;
      const usable = Math.min(width * 0.42, height * 0.62);
      const maxCm = Math.max(50, ...tags.map(t => Math.hypot(Number(t.x_cm), Number(t.y_cm))));
      const scale = usable / maxCm;

      plot.replaceChildren();

      for (let r = 50; r <= Math.ceil(maxCm / 50) * 50; r += 50) {
        plot.appendChild(svgEl('circle', {
          cx, cy, r: r * scale, fill: 'none', class: 'grid'
        }));
      }

      plot.appendChild(svgEl('line', {x1: 30, y1: cy, x2: width - 30, y2: cy, class: 'axis'}));
      plot.appendChild(svgEl('line', {x1: cx, y1: height - 30, x2: cx, y2: 30, class: 'axis'}));

      plot.appendChild(svgEl('circle', {cx, cy, r: 9, class: 'node'}));
      const nodeLabel = svgEl('text', {x: cx + 12, y: cy + 4, class: 'tag-label'});
      nodeLabel.textContent = 'node';
      plot.appendChild(nodeLabel);

      for (const tag of tags) {
        const x = Number(tag.x_cm);
        const y = Number(tag.y_cm);
        const px = cx + x * scale;
        const py = cy - y * scale;

        plot.appendChild(svgEl('line', {x1: cx, y1: cy, x2: px, y2: py, stroke: '#24394d', 'stroke-width': 1}));
        plot.appendChild(svgEl('circle', {cx: px, cy: py, r: 8, class: 'tag-dot'}));

        const label = svgEl('text', {x: px + 12, y: py - 4, class: 'tag-label'});
        label.textContent = tag.tag;
        plot.appendChild(label);

        const range = svgEl('text', {x: px + 12, y: py + 12, class: 'tag-range'});
        range.textContent = `${tag.range_cm} cm`;
        plot.appendChild(range);
      }

      const scaleLabel = svgEl('text', {x: 16, y: height - 16, class: 'tag-range'});
      scaleLabel.textContent = `scale: ${Math.round(maxCm)} cm radius`;
      plot.appendChild(scaleLabel);
    }

    async function refresh() {
      const res = await fetch('/api/samples', {cache: 'no-store'});
      const data = await res.json();
      statusEl.textContent = `${data.running ? 'running' : 'stopped'} · ${data.log_file || 'no log'}`;
      rows.replaceChildren();
      empty.style.display = data.tags.length ? 'none' : 'block';
      drawPlot(data.tags);
      for (const tag of data.tags) {
        const tr = document.createElement('tr');
        if (tag.age_s > 5) tr.classList.add('stale');
        tr.append(
          cell(tag.tag),
          cell(`${tag.age_s}s`),
          cell(tag.seq),
          cell(tag.range_cm),
          cell(tag.range_avg_cm),
          cell(tag.range_std_cm),
          cell(tag.pdoa_deg),
          cell(tag.bearing_deg),
          cell(tag.x_cm),
          cell(tag.y_cm),
          cell(Number(tag.clk_ppm).toFixed(2)),
          cell(tag.t_us)
        );
        rows.appendChild(tr);
      }
    }

    refresh();
    setInterval(refresh, 500);
  </script>
</body>
</html>
"""


class App:
    def __init__(self, root: Path, device: str, host: str, port: int, auto_start: bool, stddev_window: int):
        self.root = root
        self.device = device
        self.host = host
        self.port = port
        self.stddev_window = stddev_window
        self.log_dir = root / "logs"
        self.monitor = None
        if auto_start:
            self.start_monitor()

    def latest_log(self):
        logs = sorted(self.log_dir.glob("pdoa_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        return logs[0] if logs else None

    def start_monitor(self):
        if self.monitor and self.monitor.poll() is None:
            return
        self.log_dir.mkdir(exist_ok=True)
        cmd = [
            str(self.root / "pdoa-monitor"),
            "-d",
            self.device,
            "--stream",
            "--log-dir",
            str(self.log_dir),
        ]
        self.monitor = subprocess.Popen(
            cmd,
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def stop_monitor(self):
        if not self.monitor or self.monitor.poll() is not None:
            return
        os.killpg(self.monitor.pid, signal.SIGTERM)
        try:
            self.monitor.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(self.monitor.pid, signal.SIGKILL)
            self.monitor.wait(timeout=2)

    def running(self):
        return bool(self.monitor and self.monitor.poll() is None)

    def samples(self):
        path = self.latest_log()
        latest_by_tag = {}
        ranges_by_tag = defaultdict(lambda: deque(maxlen=self.stddev_window))
        if path:
            with path.open(newline="") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    if row.get("x_cm") == "0" and row.get("y_cm") == "0":
                        continue
                    tag = row["tag"]
                    latest_by_tag[tag] = row
                    try:
                        ranges_by_tag[tag].append(float(row["range_cm"]))
                    except (KeyError, TypeError, ValueError):
                        pass

        now = time.time()
        tags = []
        for tag, row in sorted(latest_by_tag.items()):
            try:
                x_cm = float(row["x_cm"])
                y_cm = float(row["y_cm"])
                row["bearing_deg"] = f"{math.degrees(math.atan2(y_cm, x_cm)):.0f}"
            except (KeyError, TypeError, ValueError):
                row["bearing_deg"] = "0"
            ranges = list(ranges_by_tag[tag])
            if ranges:
                mean = sum(ranges) / len(ranges)
                row["range_avg_cm"] = f"{mean:.1f}"
            else:
                mean = 0.0
                row["range_avg_cm"] = "0.0"
            if len(ranges) >= 2:
                variance = sum((value - mean) ** 2 for value in ranges) / (len(ranges) - 1)
                row["range_std_cm"] = f"{math.sqrt(variance):.1f}"
            else:
                row["range_std_cm"] = "0.0"
            try:
                sample_time = time.mktime(time.strptime(row["time"][:19], "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                sample_time = now
            row["age_s"] = max(0, int(now - sample_time))
            if row["age_s"] <= 5:
                tags.append(row)

        return {
            "running": self.running(),
            "log_file": path.name if path else None,
            "tags": tags,
        }


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/samples":
                self._json(app.samples())
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/start":
                app.start_monitor()
                self._json({"running": app.running()})
            elif path == "/api/stop":
                app.stop_monitor()
                self._json({"running": app.running()})
            else:
                self.send_error(404)

        def log_message(self, fmt, *args):
            return

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("-d", "--device", default="/dev/ttyACM0")
    parser.add_argument("--no-auto-start", action="store_true")
    parser.add_argument("--stddev-window", type=int, default=100)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    app = App(root, args.device, args.host, args.port, not args.no_auto_start, max(2, args.stddev_window))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_monitor()
        server.server_close()


if __name__ == "__main__":
    main()
