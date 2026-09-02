#!/usr/bin/env python3
import argparse
from collections import defaultdict, deque
import csv
from datetime import datetime
import io
import json
import math
import os
import re
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


TAG_LAYOUT = [
    {"tag": "dw00", "bearing_deg": 15},
    {"tag": "dw01", "bearing_deg": 35},
    {"tag": "dw02", "bearing_deg": 55},
    {"tag": "dw03", "bearing_deg": 75},
    {"tag": "dw04", "bearing_deg": 90},
    {"tag": "dw05", "bearing_deg": 105},
    {"tag": "dw06", "bearing_deg": 125},
    {"tag": "dw07", "bearing_deg": 145},
    {"tag": "dw08", "bearing_deg": 165},
]
DISTANCES_M = list(range(2, 31, 2))
ROTATIONS_DEG = [0, 90, 180, 270]
RAW_FIELDS = ["time", "tag", "a16", "seq", "range_cm", "pdoa_deg", "x_cm", "y_cm", "clk_ppm", "t_us"]
TAG_STALE_AFTER_S = 60
DRONE_BINARY = Path("/opt/dji-rpi-payload/.build/3.9.2/dji_rpi_telemetry")
DRONE_SOURCE_FIELDS = [
    "fc_timestamp_ms", "drone_model", "firmware", "bearing_deg",
    "fused_lat_deg", "fused_lon_deg", "fused_alt_m", "height_fusion_m",
    "rtk_lat_deg", "rtk_lon_deg", "rtk_h_m", "rtk_status",
]
DRONE_REFERENCE_FIELDS = ["origin_lat_deg", "origin_lon_deg", "q4_lat_deg", "q4_lon_deg"]
DRONE_UWB_WINDOW_S = 0.1


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#ffffff">
  <title>UWB Field Run</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f4f6f7; color: #1b2329; letter-spacing: 0; }
    button, input, select { font: inherit; letter-spacing: 0; }
    button { min-height: 48px; border: 0; border-radius: 6px; font-weight: 700; cursor: pointer; }
    button:disabled { cursor: not-allowed; opacity: .42; }
    header { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between; min-height: 58px; padding: 10px 16px; border-bottom: 1px solid #cbd2d7; background: #ffffff; }
    h1 { margin: 0; font-size: 18px; }
    h2 { margin: 0; font-size: 18px; }
    h3 { margin: 0 0 12px; font-size: 14px; color: #53616a; text-transform: uppercase; }
    .connection { display: flex; align-items: center; gap: 7px; color: #53616a; font-size: 13px; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: #707b83; }
    .dot.online { background: #187a40; }
    main { width: min(100%, 720px); margin: 0 auto; padding: 16px 16px calc(28px + env(safe-area-inset-bottom)); }
    section { padding: 18px 0; border-bottom: 1px solid #d6dce0; }
    .panel { border: 1px solid #cbd2d7; border-radius: 8px; padding: 16px; background: #ffffff; }
    .stack { display: grid; gap: 14px; }
    label { display: grid; gap: 7px; color: #3e4a52; font-size: 14px; }
    input, select { width: 100%; min-height: 48px; padding: 0 12px; border: 1px solid #7c8992; border-radius: 6px; background: #ffffff; color: #151b20; }
    .primary { width: 100%; color: #ffffff; background: #176b3a; }
    .warning { width: 100%; color: #2f2306; background: #e5b83f; }
    .danger { width: 100%; color: #fff; background: #9f3841; }
    .secondary { color: #1b2329; background: #dce2e5; }
    .text-button { min-height: 38px; padding: 0 8px; color: #355d7a; background: transparent; }
    .segmented { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .segmented.four { grid-template-columns: repeat(4, 1fr); }
    .segmented button { min-width: 0; color: #253039; background: #dce2e5; }
    .segmented button.selected { color: #ffffff; background: #176b3a; }
    .stepper { display: grid; grid-template-columns: 52px 1fr 52px; gap: 8px; align-items: stretch; }
    .stepper button { font-size: 24px; color: #1b2329; background: #dce2e5; }
    .step-value { display: grid; place-items: center; min-height: 58px; border: 1px solid #7c8992; border-radius: 6px; background: #ffffff; font-size: 24px; font-weight: 750; font-variant-numeric: tabular-nums; }
    .summary { display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }
    .muted { color: #5d6971; }
    .metric { font-size: 28px; font-weight: 760; font-variant-numeric: tabular-nums; }
    .tag-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin-top: 12px; }
    .tag { display: grid; grid-template-columns: 1fr; gap: 3px; padding: 10px; border: 1px solid #aab4ba; border-radius: 6px; color: #59666e; background: #ffffff; font-size: 13px; font-variant-numeric: tabular-nums; }
    .tag.ready { border-color: #28784a; color: #173b26; background: #edf8f1; }
    .tag.stale { border-color: #b78316; color: #5a4108; background: #fff6da; }
    .tag strong { font-weight: 750; }
    .tag-angle { color: #1b2329; font-size: 16px; font-weight: 750; }
    .tag-status { grid-column: 1 / -1; color: #5d6971; font-size: 11px; }
    .node-check { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; padding: 13px; border: 1px solid #aab4ba; border-radius: 6px; background: #ffffff; }
    .node-check.ready { border-color: #28784a; background: #edf8f1; }
    .node-name { display: grid; gap: 2px; }
    .node-state { font-weight: 750; color: #59666e; }
    .node-check.ready .node-state { color: #176b3a; }
    .progress-track { height: 10px; overflow: hidden; margin: 14px 0 8px; border-radius: 5px; background: #d3dade; }
    .progress-fill { width: 0; height: 100%; background: #176b3a; transition: width .25s ease; }
    .run-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
    .run-state { color: #176b3a; font-size: 13px; font-weight: 700; text-transform: uppercase; }
    .distance-row { display: grid; grid-template-columns: 48px 1fr; gap: 10px; align-items: center; padding: 9px 0; border-bottom: 1px solid #d9dee1; }
    .distance-row:last-child { border: 0; }
    .distance-label { font-size: 14px; font-weight: 700; }
    .run-dots { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
    .run-dot { display: grid; place-items: center; min-height: 32px; border: 1px solid #aab4ba; border-radius: 5px; color: #59666e; background: #ffffff; font-size: 11px; }
    .run-dot.complete { border-color: #28784a; color: #173b26; background: #edf8f1; }
    .run-dot.partial { border-color: #9a721b; color: #5a4108; background: #fff6da; }
    .run-dot.active { border-color: #397da8; color: #173b52; background: #eaf5fb; }
    .run-dot.selected { outline: 3px solid #255f86; outline-offset: 1px; font-weight: 800; }
    details summary { padding: 4px 0; color: #45535c; cursor: pointer; }
    .live-row { display: grid; grid-template-columns: 1fr repeat(3, 62px); gap: 6px; padding: 9px 0; border-bottom: 1px solid #d9dee1; font-size: 13px; font-variant-numeric: tabular-nums; }
    .live-row span:not(:first-child) { text-align: right; }
    .hidden { display: none !important; }
    .error { padding: 12px; border: 1px solid #9f3841; border-radius: 6px; color: #6d1820; background: #fff0f1; }
    dialog { width: min(calc(100% - 32px), 440px); padding: 0; border: 1px solid #aab4ba; border-radius: 8px; color: #1b2329; background: #ffffff; }
    dialog::backdrop { background: rgb(27 35 41 / 55%); }
    .dialog-content { display: grid; gap: 14px; padding: 20px; }
    .dialog-content p { margin: 0; color: #45535c; line-height: 1.45; }
    .dialog-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 4px; }
    .results-dialog { width: min(calc(100% - 24px), 560px); max-height: 88vh; }
    .results-content { max-height: 88vh; overflow: auto; }
    .result-row { display: grid; grid-template-columns: 56px 1fr; gap: 12px; padding: 12px 0; border-bottom: 1px solid #d9dee1; }
    .result-row:last-child { border-bottom: 0; }
    .result-bearing { font-size: 17px; font-weight: 800; }
    .result-values { display: grid; gap: 3px; font-size: 13px; }
    .result-values strong { font-size: 14px; }
    @media (min-width: 600px) { .tag-grid { grid-template-columns: repeat(9, 1fr); } .tag { text-align: center; padding: 10px 4px; } }
  </style>
</head>
<body>
  <header>
    <h1>UWB Field Run</h1>
    <div class="connection"><span id="connection-dot" class="dot"></span><span id="connection">Connecting</span></div>
  </header>

  <main>
    <div id="error" class="error hidden"></div>

    <section id="setup" class="hidden">
      <div class="panel stack">
        <div><h2>Field experiment</h2><div class="muted">9 tags · 60 runs</div></div>
        <label>Node height (m)<input id="node-height" type="number" value="0" min="0" step="0.1" inputmode="decimal"></label>
        <label>Dataset name<input id="dataset-name" value="ground-height-0m" maxlength="60"></label>
        <label>Samples per tag</label>
        <div id="sample-options" class="segmented">
          <button data-samples="100">100</button>
          <button class="selected" data-samples="200">200</button>
          <button data-samples="500">500</button>
        </div>
        <button id="create" class="primary">Create experiment</button>
      </div>
    </section>

    <div id="experiment" class="hidden">
      <section>
        <div class="summary">
          <div><h2 id="experiment-name"></h2><div id="experiment-height" class="muted"></div><button id="edit-experiment" class="text-button">Edit setup</button></div>
          <div style="text-align:right"><div id="overall" class="metric">0/60</div><div class="muted">runs</div></div>
        </div>
      </section>

      <section id="setup-editor" class="hidden">
        <div class="panel stack">
          <h3>Experiment setup</h3>
          <label>Node height (m)<input id="edit-node-height" type="number" min="0" step="0.1" inputmode="decimal"></label>
          <label>Dataset name<input id="edit-dataset-name" maxlength="60"></label>
          <label>Samples per tag
            <select id="edit-samples">
              <option value="100">100</option>
              <option value="200">200</option>
              <option value="500">500</option>
            </select>
          </label>
          <div class="segmented" style="grid-template-columns:1fr 1fr">
            <button id="cancel-edit" class="secondary">Cancel</button>
            <button id="save-edit" class="primary">Save setup</button>
          </div>
        </div>
      </section>

      <section id="condition" class="stack">
        <h3>Measurement</h3>
        <div class="stepper">
          <button id="distance-down" aria-label="Previous distance">−</button>
          <div id="distance" class="step-value">2 m</div>
          <button id="distance-up" aria-label="Next distance">+</button>
        </div>
        <div id="rotations" class="segmented four"></div>
      </section>

      <section>
        <h3>Node check</h3>
        <div id="node-check" class="node-check">
          <div class="node-name"><strong>DWM1002</strong><span id="node-device" class="muted">/dev/ttyACM0</span></div>
          <span id="node-state" class="node-state">Not connected</span>
        </div>
      </section>

      <section>
        <div class="summary"><h3 style="margin:0">Tag check</h3><strong id="ready-count">0 / 9 ready</strong></div>
        <div id="tag-grid" class="tag-grid"></div>
      </section>

      <section id="idle-actions">
        <button id="start-run" class="primary" disabled>Start acquisition</button>
      </section>

      <section id="active-run" class="hidden">
        <div class="panel">
          <div class="run-head"><h2 id="active-label">Collecting</h2><span class="run-state">Running</span></div>
          <div class="progress-track"><div id="run-progress" class="progress-fill"></div></div>
          <div class="summary"><span id="run-count" class="muted"></span><strong id="run-percent">0%</strong></div>
          <div id="run-tags" class="tag-grid"></div>
          <button id="stop-run" class="danger" style="margin-top:16px">Stop run</button>
        </div>
      </section>

      <section>
        <h3>Progress</h3>
        <div id="progress-list"></div>
      </section>

      <section>
        <details>
          <summary>Live measurements</summary>
          <div id="live-list"></div>
        </details>
      </section>

      <section><button id="new-experiment" class="text-button">New experiment</button></section>
    </div>
  </main>

  <dialog id="confirm-dialog">
    <div class="dialog-content">
      <h2 id="dialog-title"></h2>
      <p id="dialog-message"></p>
      <div class="dialog-actions">
        <button id="dialog-cancel" class="secondary">Cancel</button>
        <button id="dialog-overwrite" class="warning hidden">Overwrite</button>
        <button id="dialog-confirm" class="primary">Confirm</button>
      </div>
    </div>
  </dialog>

  <dialog id="results-dialog" class="results-dialog">
    <div class="dialog-content results-content">
      <div class="summary"><div><h2 id="results-title"></h2><div id="results-status" class="muted"></div></div><button id="results-close" class="text-button">Close</button></div>
      <div id="results-list"></div>
    </div>
  </dialog>

  <script>
    const tagLayout = [
      ['dw00', 15], ['dw01', 35], ['dw02', 55], ['dw03', 75], ['dw04', 90],
      ['dw05', 105], ['dw06', 125], ['dw07', 145], ['dw08', 165]
    ];
    const expectedTags = tagLayout.map(item => item[0]);
    const distances = Array.from({length: 15}, (_, i) => (i + 1) * 2);
    const rotations = [0, 90, 180, 270];
    let selectedDistance = 2;
    let selectedRotation = 0;
    let sampleTarget = 200;
    let lastActive = false;
    let datasetNameEdited = false;
    let currentExperiment = null;
    let readyTags = [];

    const el = id => document.getElementById(id);
    const setup = el('setup');
    const experiment = el('experiment');

    async function api(path, options = {}) {
      const response = await fetch(path, {cache: 'no-store', ...options});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
      return data;
    }

    async function post(path, body = {}) {
      return api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    }

    function showError(error) {
      el('error').textContent = error.message || String(error);
      el('error').classList.remove('hidden');
    }

    function clearError() { el('error').classList.add('hidden'); }

    function askConfirmation({title, message, confirmLabel = 'Confirm', tone = 'primary'}) {
      const dialog = el('confirm-dialog');
      el('dialog-overwrite').classList.add('hidden');
      el('dialog-title').textContent = title;
      el('dialog-message').textContent = message;
      el('dialog-confirm').textContent = confirmLabel;
      el('dialog-confirm').className = tone;
      dialog.showModal();
      return new Promise(resolve => {
        el('dialog-cancel').onclick = () => { dialog.close(); resolve(false); };
        el('dialog-confirm').onclick = () => { dialog.close(); resolve(true); };
        dialog.oncancel = event => { event.preventDefault(); dialog.close(); resolve(false); };
      });
    }

    function askRunAction({title, message}) {
      const dialog = el('confirm-dialog');
      el('dialog-title').textContent = title;
      el('dialog-message').textContent = message;
      el('dialog-cancel').textContent = 'Cancel';
      el('dialog-cancel').className = 'secondary';
      el('dialog-overwrite').textContent = 'Overwrite';
      el('dialog-overwrite').className = 'warning';
      el('dialog-overwrite').classList.remove('hidden');
      el('dialog-confirm').textContent = 'Continue';
      el('dialog-confirm').className = 'primary';
      dialog.showModal();
      return new Promise(resolve => {
        el('dialog-cancel').onclick = () => { dialog.close(); resolve('cancel'); };
        el('dialog-overwrite').onclick = () => { dialog.close(); resolve('overwrite'); };
        el('dialog-confirm').onclick = () => { dialog.close(); resolve('continue'); };
        dialog.oncancel = event => { event.preventDefault(); dialog.close(); resolve('cancel'); };
      });
    }

    function selectCondition(distance, rotation) {
      selectedDistance = distance;
      selectedRotation = rotation;
      el('distance').textContent = `${distance} m`;
      document.querySelectorAll('#rotations button').forEach(button => {
        button.classList.toggle('selected', Number(button.dataset.rotation) === rotation);
      });
      if (currentExperiment) renderProgress(currentExperiment);
    }

    function conditionStatus(state, distance, rotation) {
      return state.conditions[`${distance}:${rotation}`]?.status || 'pending';
    }

    async function showRunSummary(distance, rotation) {
      try {
        const summary = await api(`/api/run/summary?distance_m=${distance}&rotation_deg=${rotation}`);
        el('results-title').textContent = `${distance} m · ${rotation}°`;
        el('results-status').textContent = `${summary.status} · ${summary.file}`;
        el('results-list').replaceChildren(...summary.bearings.map(item => {
          const row = document.createElement('div');
          row.className = 'result-row';
          const range = item.samples ? `${item.range_avg_cm} ± ${item.range_std_cm} cm` : 'No valid samples';
          const pdoa = item.samples ? `${item.pdoa_mean_deg}° PDoA` : '—';
          row.innerHTML = `<div class="result-bearing">${item.bearing_deg}°</div><div class="result-values"><strong>${item.tag} · ${item.samples} samples</strong><span>${range}</span><span>${pdoa}</span></div>`;
          return row;
        }));
        el('results-dialog').showModal();
      } catch (error) { showError(error); }
    }

    function renderTags(tags) {
      readyTags = tags.filter(tag => tag.age_s <= 1).map(tag => tag.tag);
      const byName = Object.fromEntries(tags.map(tag => [tag.tag, tag]));
      el('tag-grid').replaceChildren(...tagLayout.map(([name, bearing]) => {
        const item = document.createElement('div');
        const tag = byName[name];
        const statusClass = tag ? (tag.age_s <= 1 ? ' ready' : ' stale') : '';
        const statusText = !tag ? 'No samples' : tag.age_s <= 1 ? 'Online' : `Last seen ${tag.age_s}s ago`;
        item.className = `tag${statusClass}`;
        item.innerHTML = `<span class="tag-angle">${bearing}°</span><strong>${name}</strong><span class="tag-status">${statusText}</span>`;
        return item;
      }));
      el('ready-count').textContent = `${readyTags.length} / 9 ready`;
      el('start-run').className = 'primary';
      el('start-run').textContent = 'Start acquisition';

      el('live-list').replaceChildren(...expectedTags.map(name => {
        const tag = byName[name];
        const row = document.createElement('div');
        row.className = 'live-row';
        row.innerHTML = `<strong>${name}</strong><span>${tag ? `${tag.range_cm} cm` : '—'}</span><span>${tag ? `${tag.pdoa_deg}°` : '—'}</span><span>${tag ? `${tag.age_s}s` : '—'}</span>`;
        return row;
      }));
    }

    function renderProgress(state) {
      const recorded = Object.values(state.conditions).filter(item => ['complete', 'partial'].includes(item.status)).length;
      el('overall').textContent = `${recorded}/60`;
      el('progress-list').replaceChildren(...distances.map(distance => {
        const row = document.createElement('div');
        row.className = 'distance-row';
        const dots = rotations.map(rotation => {
          const status = conditionStatus(state, distance, rotation);
          const selected = distance === selectedDistance && rotation === selectedRotation ? ' selected' : '';
          return `<button class="run-dot ${status}${selected}" data-distance="${distance}" data-rotation="${rotation}">${rotation}°</button>`;
        }).join('');
        row.innerHTML = `<div class="distance-label">${distance} m</div><div class="run-dots">${dots}</div>`;
        return row;
      }));
      document.querySelectorAll('.run-dot').forEach(button => {
        button.onclick = () => {
          const distance = Number(button.dataset.distance);
          const rotation = Number(button.dataset.rotation);
          selectCondition(distance, rotation);
          const status = conditionStatus(state, distance, rotation);
          if (status === 'complete' || status === 'partial') showRunSummary(distance, rotation);
        };
      });
    }

    function renderRun(active) {
      const running = Boolean(active);
      el('condition').classList.toggle('hidden', running);
      el('idle-actions').classList.toggle('hidden', running);
      el('active-run').classList.toggle('hidden', !running);
      if (!active) return;

      const counts = active.counts || {};
      const participating = active.participating_tags || expectedTags;
      const total = participating.reduce((sum, tag) => sum + Math.min(counts[tag] || 0, active.target_samples), 0);
      const targetTotal = participating.length * active.target_samples;
      const completedTags = participating.filter(tag => (counts[tag] || 0) >= active.target_samples).length;
      const percent = targetTotal ? Math.min(100, Math.floor(total * 100 / targetTotal)) : 0;
      el('active-label').textContent = `${active.distance_m} m · ${active.rotation_deg}°`;
      el('run-progress').style.width = `${percent}%`;
      el('run-count').textContent = `${total} / ${targetTotal} total samples · ${completedTags} / ${participating.length} tags complete`;
      el('run-percent').textContent = `${percent}%`;
      el('run-tags').replaceChildren(...expectedTags.map(name => {
        const item = document.createElement('div');
        item.className = `tag${(counts[name] || 0) > 0 ? ' ready' : ''}`;
        item.innerHTML = `<strong>${name}</strong><span>${counts[name] || 0}</span>`;
        return item;
      }));
    }

    function render(data) {
      clearError();
      el('connection-dot').classList.toggle('online', data.running);
      el('connection').textContent = data.running ? 'Connected' : 'Monitor stopped';
      el('node-check').classList.toggle('ready', data.running);
      el('node-state').textContent = data.running ? 'Ready' : 'Not connected';
      el('node-device').textContent = data.device || '/dev/ttyACM0';
      el('start-run').disabled = !data.running;
      renderTags(data.tags || []);

      if (!data.experiment) {
        setup.classList.remove('hidden');
        experiment.classList.add('hidden');
        return;
      }

      setup.classList.add('hidden');
      experiment.classList.remove('hidden');
      const state = data.experiment;
      currentExperiment = state;
      el('experiment-name').textContent = state.name;
      el('experiment-height').textContent = `Node height ${state.node_height_m} m`;
      sampleTarget = state.target_samples;
      renderProgress(state);
      renderRun(state.active_run);

      if (lastActive && !state.active_run && data.next_condition) {
        selectCondition(data.next_condition.distance_m, data.next_condition.rotation_deg);
      } else if (!lastActive && !state.active_run && !window.conditionInitialized) {
        const next = data.next_condition || {distance_m: 2, rotation_deg: 0};
        selectCondition(next.distance_m, next.rotation_deg);
        window.conditionInitialized = true;
      }
      lastActive = Boolean(state.active_run);
    }

    async function refresh() {
      try { render(await api('/api/experiment')); }
      catch (error) { el('connection-dot').classList.remove('online'); el('connection').textContent = 'Offline'; showError(error); }
    }

    for (const rotation of rotations) {
      const button = document.createElement('button');
      button.dataset.rotation = rotation;
      button.textContent = `${rotation}°`;
      button.onclick = () => selectCondition(selectedDistance, rotation);
      el('rotations').appendChild(button);
    }
    selectCondition(2, 0);

    el('distance-down').onclick = () => {
      const index = Math.max(0, distances.indexOf(selectedDistance) - 1);
      selectCondition(distances[index], selectedRotation);
    };
    el('distance-up').onclick = () => {
      const index = Math.min(distances.length - 1, distances.indexOf(selectedDistance) + 1);
      selectCondition(distances[index], selectedRotation);
    };
    document.querySelectorAll('#sample-options button').forEach(button => {
      button.onclick = () => {
        sampleTarget = Number(button.dataset.samples);
        document.querySelectorAll('#sample-options button').forEach(item => item.classList.toggle('selected', item === button));
      };
    });
    el('dataset-name').addEventListener('input', () => { datasetNameEdited = true; });
    el('node-height').addEventListener('input', () => {
      if (!datasetNameEdited) el('dataset-name').value = `ground-height-${el('node-height').value || 0}m`;
    });
    el('create').onclick = async () => {
      try {
        await post('/api/experiment/create', {
          name: el('dataset-name').value,
          node_height_m: Number(el('node-height').value),
          target_samples: sampleTarget
        });
        window.conditionInitialized = false;
        await refresh();
      } catch (error) { showError(error); }
    };
    el('edit-experiment').onclick = () => {
      el('edit-node-height').value = currentExperiment.node_height_m;
      el('edit-dataset-name').value = currentExperiment.name;
      el('edit-samples').value = currentExperiment.target_samples;
      el('setup-editor').classList.remove('hidden');
      el('setup-editor').scrollIntoView({behavior: 'smooth'});
    };
    el('cancel-edit').onclick = () => el('setup-editor').classList.add('hidden');
    el('save-edit').onclick = async () => {
      try {
        await post('/api/experiment/update', {
          name: el('edit-dataset-name').value,
          node_height_m: Number(el('edit-node-height').value),
          target_samples: Number(el('edit-samples').value)
        });
        el('setup-editor').classList.add('hidden');
        await refresh();
      } catch (error) { showError(error); }
    };
    el('start-run').onclick = async () => {
      const condition = currentExperiment.conditions[`${selectedDistance}:${selectedRotation}`] || {};
      let mode = 'overwrite';
      if (condition.status === 'partial') {
        const action = await askRunAction({
          title: 'Resume partial run?',
          message: 'Continue with the tags below target, or overwrite the saved run?'
        });
        if (action === 'cancel') return;
        mode = action;
      } else if (condition.status === 'complete') {
        if (!await askConfirmation({
          title: 'Overwrite completed run?',
          message: 'The saved measurements for this distance and rotation will be replaced.',
          confirmLabel: 'Overwrite',
          tone: 'warning'
        })) return;
      }
      try { await post('/api/run/start', {distance_m: selectedDistance, rotation_deg: selectedRotation, mode}); await refresh(); }
      catch (error) { showError(error); }
    };
    el('stop-run').onclick = async () => {
      if (!await askConfirmation({
        title: 'Stop acquisition?',
        message: 'Samples collected so far will be saved as a partial run.',
        confirmLabel: 'Stop and save',
        tone: 'danger'
      })) return;
      try { await post('/api/run/stop'); await refresh(); }
      catch (error) { showError(error); }
    };
    el('new-experiment').onclick = async () => {
      if (!await askConfirmation({
        title: 'Create new experiment?',
        message: 'The current experiment files will remain stored on the Raspberry Pi.',
        confirmLabel: 'New experiment'
      })) return;
      try { await post('/api/experiment/clear'); window.conditionInitialized = false; await refresh(); }
      catch (error) { showError(error); }
    };
    el('results-close').onclick = () => el('results-dialog').close();

    refresh();
    setInterval(refresh, 750);
  </script>
</body>
</html>
"""


DRONE_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#ffffff">
  <title>Drone Tracking</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #1b2329; background: #f4f6f7; }
    header { display: flex; align-items: center; justify-content: space-between; min-height: 58px; padding: 10px 16px; border-bottom: 1px solid #cbd2d7; background: #fff; }
    h1, h2 { margin: 0; } h1 { font-size: 18px; } h2 { font-size: 15px; text-transform: uppercase; color: #53616a; }
    main { width: min(100%, 720px); margin: 0 auto; padding: 16px 16px 32px; }
    section { padding: 18px 0; border-bottom: 1px solid #d6dce0; }
    .panel { padding: 16px; border: 1px solid #cbd2d7; border-radius: 8px; background: #fff; }
    .summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .status { color: #59666e; font-size: 13px; font-weight: 750; text-transform: uppercase; }
    .status.recording { color: #176b3a; } .status.paused { color: #9a721b; }
    .metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin-top: 14px; }
    .metric { min-height: 52px; padding: 9px; border: 1px solid #d6dce0; border-radius: 6px; background: #fbfcfc; }
    .metric span { display: block; color: #5d6971; font-size: 11px; } .metric strong { display: block; margin-top: 2px; font-size: 15px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
    .controls { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin-top: 14px; }
    button { min-height: 48px; border: 0; border-radius: 6px; font: inherit; font-weight: 750; cursor: pointer; }
    button:disabled { cursor: not-allowed; opacity: .42; }
    .primary { color: #fff; background: #176b3a; } .warning { color: #2f2306; background: #e5b83f; } .danger { color: #fff; background: #9f3841; }
    .back { color: #355d7a; font-size: 13px; font-weight: 700; text-decoration: none; }
    .reference-grid { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 10px; margin-top: 14px; }
    .reference-point { display: grid; min-height: 58px; align-content: center; padding: 9px; border: 1px solid #d6dce0; border-radius: 6px; background: #fbfcfc; }
    .reference-point span { color: #5d6971; font-size: 11px; }
    .reference-point strong { margin-top: 2px; font-size: 14px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
    .reference-grid button { min-width: 118px; min-height: 58px; }
    .tag-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin-top: 12px; }
    .tag { display: grid; gap: 3px; min-height: 94px; padding: 10px; border: 1px solid #aab4ba; border-radius: 6px; color: #59666e; background: #fff; font-size: 13px; font-variant-numeric: tabular-nums; }
    .tag.ready { border-color: #28784a; color: #173b26; background: #edf8f1; } .tag.stale { border-color: #b78316; color: #5a4108; background: #fff6da; }
    .tag-angle { font-size: 16px; font-weight: 750; } .tag-status { color: #5d6971; font-size: 11px; }
    .muted { color: #5d6971; font-size: 13px; } .error { margin-top: 12px; color: #6d1820; font-size: 13px; }
    @media (min-width: 600px) { .metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); } .tag-grid { grid-template-columns: repeat(9, 1fr); } .tag { text-align: center; padding: 10px 4px; } }
  </style>
</head>
<body>
  <header><h1>Drone Tracking</h1><a class="back" href="/">Field runs</a></header>
  <main>
    <section>
      <div class="panel">
        <div class="summary"><h2>Local reference</h2><span id="reference-state" class="muted">Not set</span></div>
        <div class="reference-grid">
          <div class="reference-point"><span>O · Local (0, 0)</span><strong id="origin-value">Not captured</strong></div><button id="capture-origin" class="primary">Capture O</button>
          <div class="reference-point"><span>Q4 · +Y direction</span><strong id="q4-value">Not captured</strong></div><button id="capture-q4" class="primary">Capture Q4</button>
        </div>
      </div>
    </section>
    <section>
      <div class="panel">
        <div class="summary"><h2>Matrice 300 RTK</h2><span id="state" class="status">Stopped</span></div>
        <div id="metrics" class="metrics"></div>
        <div class="controls"><button id="start" class="primary">Start</button><button id="pause" class="warning">Pause</button><button id="stop" class="danger">Stop</button></div>
        <div id="log-file" class="muted" style="margin-top:10px">No recording</div>
        <div id="error" class="error"></div>
      </div>
    </section>
    <section><div class="summary"><h2>UWB tags</h2><strong id="tag-count" class="muted">0 / 9 live</strong></div><div id="tags" class="tag-grid"></div></section>
  </main>
  <script>
    const layout = [['dw00',15],['dw01',35],['dw02',55],['dw03',75],['dw04',90],['dw05',105],['dw06',125],['dw07',145],['dw08',165]];
    const el = id => document.getElementById(id);
    const fields = [['fused_lat_deg','Latitude'],['fused_lon_deg','Longitude'],['height_fusion_m','Height (m)'],['bearing_deg','Bearing'],['rtk_lat_deg','RTK latitude'],['rtk_lon_deg','RTK longitude'],['rtk_h_m','RTK H (m)'],['rtk_status','RTK status'],['gt_x_m','Local X (m)'],['gt_y_m','Local Y (m)']];
    async function api(path, options = {}) { const response = await fetch(path, {cache:'no-store', ...options}); const data = await response.json(); if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`); return data; }
    function value(drone, key) { const raw = drone && drone[key]; if (raw === undefined || raw === null || raw === '') return '—'; if (key === 'bearing_deg') return `${raw}°`; return raw; }
    function render(data) {
      const state = data.state || 'stopped'; el('state').textContent = state; el('state').className = `status ${state}`;
      el('log-file').textContent = data.log_file ? `${state} · ${data.log_file}` : 'No recording';
      const values = {...(data.drone || {}), ...(data.ground_truth || {})}; el('metrics').replaceChildren(...fields.map(([key,label]) => { const box=document.createElement('div'); box.className='metric'; box.innerHTML=`<span>${label}</span><strong>${value(values,key)}</strong>`; return box; }));
      const points = data.reference_points || {}; const formatPoint = prefix => points[`${prefix}_lat_deg`] === undefined ? 'Not captured' : `${points[`${prefix}_lat_deg`].toFixed(8)}, ${points[`${prefix}_lon_deg`].toFixed(8)}`; el('origin-value').textContent=formatPoint('origin'); el('q4-value').textContent=formatPoint('q4'); el('reference-state').textContent=data.reference ? `Ready · ${data.reference_baseline_m.toFixed(2)} m` : 'Capture O and Q4';
      el('start').disabled = state === 'recording'; el('pause').disabled = state !== 'recording'; el('stop').disabled = state === 'stopped';
      const tags = Object.fromEntries((data.tags || []).map(tag => [tag.tag, tag])); const live = Object.values(tags).filter(tag => tag.age_s <= 1).length; el('tag-count').textContent = `${live} / 9 live`;
      el('tags').replaceChildren(...layout.map(([name,bearing]) => { const tag=tags[name]; const cls=!tag ? '' : tag.age_s <= 1 ? ' ready' : ' stale'; const text=!tag ? 'No samples' : tag.age_s <= 1 ? 'Online' : `Last seen ${tag.age_s}s ago`; const card=document.createElement('div'); card.className=`tag${cls}`; card.innerHTML=`<span class="tag-angle">${bearing}°</span><strong>${name}</strong><span>${tag ? `${tag.range_cm} cm · ${tag.pdoa_deg}°` : '—'}</span><span class="tag-status">${text}</span>`; return card; }));
    }
    async function refresh() { try { el('error').textContent=''; render(await api('/api/drone')); } catch (error) { el('error').textContent=error.message || String(error); } }
    el('start').onclick = async () => { try { await api('/api/drone/start', {method:'POST'}); await refresh(); } catch (error) { el('error').textContent=error.message; } };
    el('pause').onclick = async () => { try { await api('/api/drone/pause', {method:'POST'}); await refresh(); } catch (error) { el('error').textContent=error.message; } };
    el('stop').onclick = async () => { try { await api('/api/drone/stop', {method:'POST'}); await refresh(); } catch (error) { el('error').textContent=error.message; } };
    el('capture-origin').onclick = async () => { try { await api('/api/drone/reference/origin', {method:'POST'}); await refresh(); } catch (error) { el('error').textContent=error.message; } };
    el('capture-q4').onclick = async () => { try { await api('/api/drone/reference/q4', {method:'POST'}); await refresh(); } catch (error) { el('error').textContent=error.message; } };
    refresh(); setInterval(refresh, 500);
  </script>
</body>
</html>
"""


def parse_sample_time(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0


class App:
    def __init__(self, root: Path, device: str, host: str, port: int, auto_start: bool, stddev_window: int):
        self.root = root
        self.device = device
        self.host = host
        self.port = port
        self.stddev_window = stddev_window
        self.log_dir = root / "logs"
        self.dataset_dir = root / "datasets"
        self.state_path = self.dataset_dir / "current-experiment.json"
        self.monitor = None
        self.last_monitor_start = 0
        self.lock = threading.RLock()
        self.drone_dir = root / "drone-logs"
        self.drone_reference_path = self.drone_dir / "reference.json"
        self.drone_process = None
        self.drone_thread = None
        self.drone_state = "stopped"
        self.drone_latest = None
        self.drone_log_path = None
        self.drone_log_fp = None
        self.drone_log_writer = None
        self.uwb_latest = {}
        self.uwb_tail_path = None
        self.uwb_tail_header = ""
        self.uwb_tail_offset = 0
        if auto_start:
            self.start_monitor()

    @staticmethod
    def _drone_fields():
        return [
            "time", *DRONE_SOURCE_FIELDS, *DRONE_REFERENCE_FIELDS,
            "reference_baseline_m", "gt_x_m", "gt_y_m", "tag",
            "uwb_time", "uwb_age_s", "range_cm", "pdoa_deg", "x_cm", "y_cm", "t_us",
        ]

    def _load_drone_reference(self):
        try:
            values = json.loads(self.drone_reference_path.read_text())
            return {field: float(values[field]) for field in DRONE_REFERENCE_FIELDS}
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _drone_reference_points(self):
        try:
            values = json.loads(self.drone_reference_path.read_text())
            return {field: float(values[field]) for field in DRONE_REFERENCE_FIELDS if field in values}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}

    def update_drone_reference(self, values):
        try:
            reference = {field: float(values[field]) for field in DRONE_REFERENCE_FIELDS}
        except (KeyError, TypeError, ValueError):
            raise ValueError("Origin and Q4 latitude/longitude are required")
        if not (-90 <= reference["origin_lat_deg"] <= 90 and -90 <= reference["q4_lat_deg"] <= 90):
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if not (-180 <= reference["origin_lon_deg"] <= 180 and -180 <= reference["q4_lon_deg"] <= 180):
            raise ValueError("Longitude must be between -180 and 180 degrees")
        if reference["origin_lat_deg"] == reference["q4_lat_deg"] and reference["origin_lon_deg"] == reference["q4_lon_deg"]:
            raise ValueError("Origin and Q4 must be distinct points")
        self.drone_dir.mkdir(exist_ok=True)
        temporary = self.drone_reference_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(reference, indent=2) + "\n")
        temporary.replace(self.drone_reference_path)
        return reference

    def capture_drone_reference(self, point):
        if point not in ("origin", "q4"):
            raise ValueError("Reference point must be origin or q4")
        row = self.drone_latest or {}
        try:
            if int(row.get("rtk_status", 0)) == 0:
                raise ValueError("Waiting for a valid RTK solution")
            latitude = float(row["rtk_lat_deg"])
            longitude = float(row["rtk_lon_deg"])
            if latitude == 0 and longitude == 0:
                raise ValueError("Waiting for a valid RTK position")
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ValueError):
                raise
            raise ValueError("Waiting for a valid RTK position")
        values = self._drone_reference_points()
        values[f"{point}_lat_deg"] = latitude
        values[f"{point}_lon_deg"] = longitude
        self.drone_dir.mkdir(exist_ok=True)
        temporary = self.drone_reference_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, indent=2) + "\n")
        temporary.replace(self.drone_reference_path)
        return values

    @staticmethod
    def _local_xy(reference, latitude_deg, longitude_deg):
        radius_m = 6378137.0
        origin_lat_rad = math.radians(reference["origin_lat_deg"])
        east_m = math.radians(longitude_deg - reference["origin_lon_deg"]) * radius_m * math.cos(origin_lat_rad)
        north_m = math.radians(latitude_deg - reference["origin_lat_deg"]) * radius_m
        q4_east_m = math.radians(reference["q4_lon_deg"] - reference["origin_lon_deg"]) * radius_m * math.cos(origin_lat_rad)
        q4_north_m = math.radians(reference["q4_lat_deg"] - reference["origin_lat_deg"]) * radius_m
        length_m = math.hypot(q4_east_m, q4_north_m)
        if length_m < 0.01:
            raise ValueError("Origin and Q4 are too close")
        y_east = q4_east_m / length_m
        y_north = q4_north_m / length_m
        return east_m * y_north - north_m * y_east, east_m * y_east + north_m * y_north

    @staticmethod
    def _reference_baseline_m(reference):
        radius_m = 6378137.0
        origin_lat_rad = math.radians(reference["origin_lat_deg"])
        east_m = math.radians(reference["q4_lon_deg"] - reference["origin_lon_deg"]) * radius_m * math.cos(origin_lat_rad)
        north_m = math.radians(reference["q4_lat_deg"] - reference["origin_lat_deg"]) * radius_m
        return math.hypot(east_m, north_m)

    def _drone_ground_truth(self, drone_row, reference):
        if not reference:
            return {}
        try:
            if int(drone_row.get("rtk_status", 0)) == 0:
                return {}
            latitude = float(drone_row["rtk_lat_deg"])
            longitude = float(drone_row["rtk_lon_deg"])
            if latitude == 0 and longitude == 0:
                return {}
            x_m, y_m = self._local_xy(reference, latitude, longitude)
            return {"gt_x_m": f"{x_m:.3f}", "gt_y_m": f"{y_m:.3f}"}
        except (KeyError, TypeError, ValueError):
            return {}

    def _reset_uwb_tail(self):
        path = self.latest_log()
        self.uwb_tail_path = path
        self.uwb_tail_header = ""
        self.uwb_tail_offset = 0
        self.uwb_latest = {row["tag"]: row for row in self.samples()["tags"]}
        if not path:
            return
        try:
            with path.open() as fp:
                self.uwb_tail_header = fp.readline()
                fp.seek(0, os.SEEK_END)
                self.uwb_tail_offset = fp.tell()
        except OSError:
            self.uwb_tail_path = None

    def _tail_uwb(self):
        path = self.latest_log()
        if path != self.uwb_tail_path:
            self._reset_uwb_tail()
            return
        if not path or not self.uwb_tail_header:
            return
        try:
            with path.open() as fp:
                fp.seek(self.uwb_tail_offset)
                lines = fp.readlines()
                self.uwb_tail_offset = fp.tell()
        except OSError:
            return
        known_tags = {item["tag"] for item in TAG_LAYOUT}
        for line in lines:
            try:
                row = next(csv.DictReader(io.StringIO(self.uwb_tail_header + line)))
            except (csv.Error, StopIteration):
                continue
            if row.get("tag") in known_tags and self._valid_row(row):
                self.uwb_latest[row["tag"]] = row

    def _drone_tags(self):
        self._tail_uwb()
        now = time.time()
        tags = []
        for tag, row in sorted(self.uwb_latest.items()):
            value = dict(row)
            sample_time = parse_sample_time(value.get("time")) or now
            value["age_s"] = max(0, int(now - sample_time))
            if value["age_s"] <= TAG_STALE_AFTER_S:
                tags.append(value)
        return tags

    def _write_drone_row(self, drone_row):
        if not self.drone_log_writer:
            return
        values = {field: "" for field in self._drone_fields()}
        values["time"] = datetime.now().astimezone().isoformat(timespec="milliseconds")
        values.update({field: drone_row.get(field, "") for field in DRONE_SOURCE_FIELDS})
        reference = self._load_drone_reference()
        if reference:
            values.update(reference)
            values["reference_baseline_m"] = f"{self._reference_baseline_m(reference):.3f}"
            values.update(self._drone_ground_truth(drone_row, reference))
        self._tail_uwb()
        now = time.time()
        for item in TAG_LAYOUT:
            row = self.uwb_latest.get(item["tag"])
            if not row:
                continue
            sample_time = parse_sample_time(row.get("time")) or now
            age_s = max(0.0, now - sample_time)
            if age_s > DRONE_UWB_WINDOW_S:
                continue
            tag_values = dict(values)
            tag_values["tag"] = item["tag"]
            tag_values["uwb_time"] = row.get("time", "")
            tag_values["uwb_age_s"] = f"{age_s:.3f}"
            for field in ("range_cm", "pdoa_deg", "x_cm", "y_cm", "t_us"):
                tag_values[field] = row.get(field, "")
            self.drone_log_writer.writerow(tag_values)
        self.drone_log_fp.flush()

    def _read_drone(self, process):
        try:
            for row in csv.DictReader(process.stdout):
                if not row.get("fc_timestamp_ms"):
                    continue
                with self.lock:
                    self.drone_latest = dict(row)
                    if self.drone_state == "recording":
                        self._write_drone_row(row)
        finally:
            with self.lock:
                if process is self.drone_process:
                    self.drone_process = None
                    self.drone_thread = None
                    if self.drone_state != "stopped":
                        self.drone_state = "stopped"
                    if self.drone_log_fp:
                        self.drone_log_fp.close()
                        self.drone_log_fp = None
                        self.drone_log_writer = None

    def start_drone_tracking(self):
        with self.lock:
            if self.drone_process and self.drone_process.poll() is None:
                self.drone_state = "recording"
                return self.drone_status()
            if not DRONE_BINARY.is_file():
                raise ValueError(f"Missing DJI telemetry binary: {DRONE_BINARY}")
            self._reset_uwb_tail()
            self.drone_dir.mkdir(exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            self.drone_log_path = self.drone_dir / f"drone_{stamp}.csv"
            self.drone_log_fp = self.drone_log_path.open("w", newline="")
            self.drone_log_writer = csv.DictWriter(self.drone_log_fp, fieldnames=self._drone_fields())
            self.drone_log_writer.writeheader()
            self.drone_log_fp.flush()
            self.drone_process = subprocess.Popen(
                [str(DRONE_BINARY)], cwd=DRONE_BINARY.parent, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                start_new_session=True,
            )
            self.drone_state = "recording"
            self.drone_thread = threading.Thread(target=self._read_drone, args=(self.drone_process,), daemon=True)
            self.drone_thread.start()
            return self.drone_status()

    def pause_drone_tracking(self):
        with self.lock:
            if not self.drone_process or self.drone_process.poll() is not None:
                raise ValueError("Drone tracking is not running")
            self.drone_state = "paused"
            return self.drone_status()

    def stop_drone_tracking(self):
        with self.lock:
            process = self.drone_process
            self.drone_state = "stopped"
            if self.drone_log_fp:
                self.drone_log_fp.close()
                self.drone_log_fp = None
                self.drone_log_writer = None
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            return self.drone_status()

    def drone_status(self):
        self.ensure_monitor()
        reference = self._load_drone_reference()
        return {
            "state": self.drone_state,
            "running": bool(self.drone_process and self.drone_process.poll() is None),
            "log_file": self.drone_log_path.name if self.drone_log_path else None,
            "drone": self.drone_latest,
            "reference": reference,
            "reference_points": self._drone_reference_points(),
            "reference_baseline_m": self._reference_baseline_m(reference) if reference else None,
            "ground_truth": self._drone_ground_truth(self.drone_latest or {}, reference),
            "tags": self._drone_tags(),
            "uwb_running": self.node_ready(),
            "uwb_device": self.device,
        }

    def latest_log(self):
        logs = sorted(self.log_dir.glob("pdoa_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
        return logs[0] if logs else None

    def start_monitor(self):
        if self.monitor and self.monitor.poll() is None:
            return
        self.last_monitor_start = time.time()
        if not Path(self.device).exists():
            return
        self.log_dir.mkdir(exist_ok=True)
        cmd = [
            str(self.root / "pdoa-monitor"), "-d", self.device, "--stream", "--log-dir", str(self.log_dir)
        ]
        self.monitor = subprocess.Popen(
            cmd, cwd=self.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
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

    def node_ready(self):
        return Path(self.device).exists() and self.running()

    def ensure_monitor(self):
        device_exists = Path(self.device).exists()
        if self.running() and not device_exists:
            self.stop_monitor()
        if device_exists and not self.running() and time.time() - self.last_monitor_start >= 5:
            self.start_monitor()

    def _read_rows(self, paths=None):
        rows = []
        for path in paths or ([self.latest_log()] if self.latest_log() else []):
            if not path or not path.exists():
                continue
            try:
                with path.open(newline="") as fp:
                    rows.extend(csv.DictReader(fp))
            except (OSError, csv.Error):
                continue
        return rows

    def samples(self):
        path = self.latest_log()
        latest_by_tag = {}
        ranges_by_tag = defaultdict(lambda: deque(maxlen=self.stddev_window))
        for source_row in self._read_rows([path] if path else []):
            if source_row.get("x_cm") == "0" and source_row.get("y_cm") == "0":
                continue
            row = dict(source_row)
            tag = row.get("tag")
            if not tag:
                continue
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
            mean = sum(ranges) / len(ranges) if ranges else 0.0
            row["range_avg_cm"] = f"{mean:.1f}"
            if len(ranges) >= 2:
                variance = sum((value - mean) ** 2 for value in ranges) / (len(ranges) - 1)
                row["range_std_cm"] = f"{math.sqrt(variance):.1f}"
            else:
                row["range_std_cm"] = "0.0"
            sample_time = parse_sample_time(row.get("time")) or now
            row["age_s"] = max(0, int(now - sample_time))
            if row["age_s"] <= TAG_STALE_AFTER_S and tag in {item["tag"] for item in TAG_LAYOUT}:
                tags.append(row)

        return {"running": self.node_ready(), "device": self.device, "log_file": path.name if path else None, "tags": tags}

    def _load_state(self):
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _save_state(self, state):
        self.dataset_dir.mkdir(exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(self.state_path)

    def create_experiment(self, name, target_samples, node_height_m=0):
        name = str(name or "ground-height-0").strip()
        if not name:
            raise ValueError("Dataset name is required")
        target_samples = int(target_samples)
        if target_samples not in (100, 200, 500):
            raise ValueError("Samples per tag must be 100, 200, or 500")
        node_height_m = float(node_height_m)
        if not math.isfinite(node_height_m) or node_height_m < 0:
            raise ValueError("Node height must be a non-negative number")
        if node_height_m.is_integer():
            node_height_m = int(node_height_m)
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "ground-height-0"
        experiment_id = f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}"
        state = {
            "id": experiment_id,
            "name": name,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "node_height_m": node_height_m,
            "target_samples": target_samples,
            "distances_m": DISTANCES_M,
            "rotations_deg": ROTATIONS_DEG,
            "tags": TAG_LAYOUT,
            "conditions": {
                f"{distance}:{rotation}": {"status": "pending", "attempts": 0}
                for distance in DISTANCES_M for rotation in ROTATIONS_DEG
            },
            "active_run": None,
        }
        experiment_path = self.dataset_dir / experiment_id
        (experiment_path / "runs").mkdir(parents=True, exist_ok=False)
        (experiment_path / "experiment.json").write_text(json.dumps(state, indent=2) + "\n")
        self._save_state(state)
        return state

    def clear_experiment(self):
        with self.lock:
            if self.state_path.exists():
                self.state_path.unlink()

    def update_experiment(self, name, target_samples, node_height_m):
        with self.lock:
            state = self._load_state()
            if not state:
                raise ValueError("Create an experiment first")
            if state.get("active_run") or any(
                condition.get("attempts", 0) > 0 for condition in state["conditions"].values()
            ):
                raise ValueError("Setup cannot be changed after acquisition has started")
            name = str(name or "").strip()
            if not name:
                raise ValueError("Dataset name is required")
            target_samples = int(target_samples)
            if target_samples not in (100, 200, 500):
                raise ValueError("Samples per tag must be 100, 200, or 500")
            node_height_m = float(node_height_m)
            if not math.isfinite(node_height_m) or node_height_m < 0:
                raise ValueError("Node height must be a non-negative number")
            if node_height_m.is_integer():
                node_height_m = int(node_height_m)
            state["name"] = name
            state["target_samples"] = target_samples
            state["node_height_m"] = node_height_m
            self._persist_experiment(state)
            return state

    def _experiment_path(self, state):
        return self.dataset_dir / state["id"]

    def _persist_experiment(self, state):
        self._save_state(state)
        path = self._experiment_path(state) / "experiment.json"
        path.write_text(json.dumps(state, indent=2) + "\n")

    def _run_rows(self, active):
        started_at = float(active["started_epoch"])
        known_tags = {item["tag"] for item in TAG_LAYOUT}
        rows = []
        base_file = active.get("base_file")
        if base_file:
            rows.extend(self._read_rows([self._experiment_path(self._load_state()) / "runs" / base_file]))
        paths = [path for path in self.log_dir.glob("pdoa_*.csv") if path.stat().st_mtime >= started_at - 2]
        rows.extend(
            row for row in self._read_rows(sorted(paths))
            if row.get("tag") in known_tags and parse_sample_time(row.get("time")) >= started_at
        )
        return [row for row in rows if row.get("tag") in known_tags]

    @staticmethod
    def _valid_row(row):
        try:
            return float(row.get("range_cm", 0)) > 0 and not (
                float(row.get("x_cm", 0)) == 0 and float(row.get("y_cm", 0)) == 0
            )
        except (TypeError, ValueError):
            return False

    def _counts(self, rows):
        counts = {item["tag"]: 0 for item in TAG_LAYOUT}
        for row in rows:
            if self._valid_row(row):
                counts[row["tag"]] += 1
        return counts

    def _capped_rows(self, rows, active):
        counts = defaultdict(int)
        participating = set(active["participating_tags"])
        capped = []
        for row in rows:
            tag = row.get("tag")
            if tag not in participating or not self._valid_row(row):
                continue
            if counts[tag] >= active["target_samples"]:
                continue
            counts[tag] += 1
            capped.append(row)
        return capped

    def start_run(self, distance_m, rotation_deg, mode="overwrite"):
        with self.lock:
            state = self._load_state()
            if not state:
                raise ValueError("Create an experiment first")
            if state.get("active_run"):
                raise ValueError("A run is already active")
            distance_m = int(distance_m)
            rotation_deg = int(rotation_deg)
            if distance_m not in DISTANCES_M or rotation_deg not in ROTATIONS_DEG:
                raise ValueError("Invalid distance or rotation")
            if mode not in ("continue", "overwrite"):
                raise ValueError("Invalid run mode")
            key = f"{distance_m}:{rotation_deg}"
            condition = state["conditions"][key]
            if mode == "continue" and condition.get("status") != "partial":
                raise ValueError("Only a partial run can be continued")
            base_file = condition.get("file") if mode == "continue" else None
            base_rows = []
            if base_file:
                base_path = self._experiment_path(state) / "runs" / base_file
                base_rows = self._read_rows([base_path])
            expected_tags = [item["tag"] for item in TAG_LAYOUT]
            if mode == "continue":
                participating = condition.get("participating_tags") or sorted(
                    {row["tag"] for row in base_rows if self._valid_row(row)}
                )
                ready_tags = sorted(row["tag"] for row in self.samples()["tags"] if row["tag"] in participating)
                participating_tags = participating
                missing_tags = condition.get("missing_tags", [
                    tag for tag in expected_tags if tag not in participating_tags
                ])
            else:
                ready_tags = sorted(row["tag"] for row in self.samples()["tags"])
                participating_tags = expected_tags
                missing_tags = [tag for tag in expected_tags if tag not in ready_tags]
            attempt = state["conditions"][key]["attempts"] + 1
            state["conditions"][key] = {"status": "active", "attempts": attempt}
            active_run = {
                "distance_m": distance_m,
                "rotation_deg": rotation_deg,
                "attempt": attempt,
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "started_epoch": time.time(),
                "target_samples": state["target_samples"],
                "participating_tags": participating_tags,
                "missing_tags": missing_tags,
                "base_file": base_file,
                "counts": {item["tag"]: 0 for item in TAG_LAYOUT},
            }
            if base_rows:
                active_run["counts"] = self._counts(self._capped_rows(base_rows, active_run))
            elif mode == "continue":
                active_run["counts"] = {
                    tag: min(int(condition.get("counts", {}).get(tag, 0)), state["target_samples"])
                    for tag in expected_tags
                }
            state["active_run"] = active_run
            self._persist_experiment(state)
            return state["active_run"]

    def _finish_run(self, state, status, rows=None):
        active = state["active_run"]
        rows = self._run_rows(active) if rows is None else rows
        rows = self._capped_rows(rows, active)
        counts = self._counts(rows)
        key = f"{active['distance_m']}:{active['rotation_deg']}"
        filename = (
            f"d{active['distance_m']:03d}m_r{active['rotation_deg']:03d}_"
            f"run{active['attempt']:02d}.csv"
        )
        output = self._experiment_path(state) / "runs" / filename
        bearings = {item["tag"]: item["bearing_deg"] for item in TAG_LAYOUT}
        fields = [
            "experiment_id", "run_file", "node_height_m", "target_distance_m", "tag_rotation_deg",
            "expected_tags", "participating_tags", "missing_tags", "tag_bearing_deg", "valid_position", *RAW_FIELDS,
        ]
        with output.open("w", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "experiment_id": state["id"],
                    "run_file": filename,
                    "node_height_m": state["node_height_m"],
                    "target_distance_m": active["distance_m"],
                    "tag_rotation_deg": active["rotation_deg"],
                    "expected_tags": ";".join(item["tag"] for item in TAG_LAYOUT),
                    "participating_tags": ";".join(active["participating_tags"]),
                    "missing_tags": ";".join(active["missing_tags"]),
                    "tag_bearing_deg": bearings[row["tag"]],
                    "valid_position": int(self._valid_row(row)),
                    **{field: row.get(field, "") for field in RAW_FIELDS},
                })
        state["conditions"][key] = {
            "status": status,
            "attempts": active["attempt"],
            "file": filename,
            "counts": counts,
            "participating_tags": active["participating_tags"],
            "missing_tags": active["missing_tags"],
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        state["active_run"] = None
        self._persist_experiment(state)

    def stop_run(self):
        with self.lock:
            state = self._load_state()
            if not state or not state.get("active_run"):
                raise ValueError("No run is active")
            self._finish_run(state, "partial")

    def run_summary(self, distance_m, rotation_deg):
        with self.lock:
            state = self._load_state()
            if not state:
                raise ValueError("Create an experiment first")
            distance_m = int(distance_m)
            rotation_deg = int(rotation_deg)
            if distance_m not in DISTANCES_M or rotation_deg not in ROTATIONS_DEG:
                raise ValueError("Invalid distance or rotation")
            condition = state["conditions"][f"{distance_m}:{rotation_deg}"]
            filename = condition.get("file")
            if not filename:
                raise ValueError("This condition has no recorded run")
            path = self._experiment_path(state) / "runs" / filename
            rows_by_tag = defaultdict(list)
            for row in self._read_rows([path]):
                if row.get("valid_position") == "1":
                    rows_by_tag[row["tag"]].append(row)

            bearings = []
            for layout in TAG_LAYOUT:
                rows = rows_by_tag[layout["tag"]]
                ranges = [float(row["range_cm"]) for row in rows]
                pdoa_values = [math.radians(float(row["pdoa_deg"])) for row in rows]
                mean = sum(ranges) / len(ranges) if ranges else 0.0
                if len(ranges) >= 2:
                    variance = sum((value - mean) ** 2 for value in ranges) / (len(ranges) - 1)
                    stddev = math.sqrt(variance)
                else:
                    stddev = 0.0
                if pdoa_values:
                    pdoa_mean = math.degrees(math.atan2(
                        sum(math.sin(value) for value in pdoa_values),
                        sum(math.cos(value) for value in pdoa_values),
                    ))
                else:
                    pdoa_mean = 0.0
                bearings.append({
                    "tag": layout["tag"],
                    "bearing_deg": layout["bearing_deg"],
                    "samples": len(rows),
                    "range_avg_cm": f"{mean:.1f}",
                    "range_std_cm": f"{stddev:.1f}",
                    "pdoa_mean_deg": f"{pdoa_mean:.1f}",
                })
            return {
                "distance_m": distance_m,
                "rotation_deg": rotation_deg,
                "status": condition["status"],
                "file": filename,
                "bearings": bearings,
            }

    def clear_runs(self, confirmation):
        with self.lock:
            if confirmation != "DELETE_ALL_RUNS":
                raise ValueError("Confirmation must be DELETE_ALL_RUNS")
            state = self._load_state()
            if not state:
                raise ValueError("Create an experiment first")
            if state.get("active_run"):
                raise ValueError("Stop the active run before deleting saved runs")
            runs_dir = self._experiment_path(state) / "runs"
            files = list(runs_dir.glob("*.csv"))
            for path in files:
                path.unlink()
            state["conditions"] = {
                f"{distance}:{rotation}": {"status": "pending", "attempts": 0}
                for distance in DISTANCES_M for rotation in ROTATIONS_DEG
            }
            self._persist_experiment(state)
            return {"deleted_runs": len(files), "experiment_id": state["id"]}

    def experiment_status(self):
        self.ensure_monitor()
        with self.lock:
            state = self._load_state()
            if state and state.get("active_run"):
                rows = self._run_rows(state["active_run"])
                rows = self._capped_rows(rows, state["active_run"])
                counts = self._counts(rows)
                state["active_run"]["counts"] = counts
                participating = state["active_run"]["participating_tags"]
                target_reached = min(counts[tag] for tag in participating) >= state["active_run"]["target_samples"]
                if target_reached:
                    run_status = "complete"
                    self._finish_run(state, run_status, rows)
                    state = self._load_state()
                else:
                    self._persist_experiment(state)
            sample_data = self.samples()
            next_condition = None
            if state:
                for distance in DISTANCES_M:
                    for rotation in ROTATIONS_DEG:
                        if state["conditions"][f"{distance}:{rotation}"]["status"] == "pending":
                            next_condition = {"distance_m": distance, "rotation_deg": rotation}
                            break
                    if next_condition:
                        break
                if not next_condition:
                    for distance in DISTANCES_M:
                        for rotation in ROTATIONS_DEG:
                            if state["conditions"][f"{distance}:{rotation}"]["status"] == "partial":
                                next_condition = {"distance_m": distance, "rotation_deg": rotation}
                                break
                        if next_condition:
                            break
            return {**sample_data, "experiment": state, "next_condition": next_condition}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                raise ValueError("Invalid JSON body")

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/drone":
                body = DRONE_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/samples":
                self._json(app.samples())
            elif path == "/api/drone":
                self._json(app.drone_status())
            elif path == "/api/experiment":
                self._json(app.experiment_status())
            elif path == "/api/run/summary":
                try:
                    query = parse_qs(parsed.query)
                    self._json(app.run_summary(query["distance_m"][0], query["rotation_deg"][0]))
                except (KeyError, TypeError, ValueError) as error:
                    self._json({"error": str(error)}, 400)
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
                if path == "/api/start":
                    app.start_monitor()
                    self._json({"running": app.node_ready()})
                elif path == "/api/drone/start":
                    self._json(app.start_drone_tracking())
                elif path == "/api/drone/pause":
                    self._json(app.pause_drone_tracking())
                elif path == "/api/drone/stop":
                    self._json(app.stop_drone_tracking())
                elif path == "/api/drone/reference":
                    self._json(app.update_drone_reference(body))
                elif path == "/api/drone/reference/origin":
                    self._json(app.capture_drone_reference("origin"))
                elif path == "/api/drone/reference/q4":
                    self._json(app.capture_drone_reference("q4"))
                elif path == "/api/stop":
                    app.stop_monitor()
                    self._json({"running": app.node_ready()})
                elif path == "/api/experiment/create":
                    self._json(app.create_experiment(
                        body.get("name"), body.get("target_samples", 200), body.get("node_height_m", 0)
                    ), 201)
                elif path == "/api/experiment/clear":
                    app.clear_experiment()
                    self._json({"ok": True})
                elif path == "/api/experiment/update":
                    self._json(app.update_experiment(
                        body.get("name"), body.get("target_samples"), body.get("node_height_m")
                    ))
                elif path == "/api/run/start":
                    self._json(app.start_run(
                        body.get("distance_m"), body.get("rotation_deg"), body.get("mode", "overwrite")
                    ), 201)
                elif path == "/api/run/stop":
                    app.stop_run()
                    self._json({"ok": True})
                elif path == "/api/runs/clear":
                    self._json(app.clear_runs(body.get("confirm")))
                else:
                    self.send_error(404)
            except (KeyError, TypeError, ValueError) as error:
                self._json({"error": str(error)}, 400)

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
