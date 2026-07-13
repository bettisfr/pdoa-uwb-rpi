#!/usr/bin/env python3
import argparse
from collections import defaultdict, deque
import csv
from datetime import datetime
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
RUN_TIMEOUT_S = 120
RAW_FIELDS = ["time", "tag", "a16", "seq", "range_cm", "pdoa_deg", "x_cm", "y_cm", "clk_ppm", "t_us"]


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
    .dialog-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 4px; }
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
      readyTags = tags.map(tag => tag.tag);
      const byName = Object.fromEntries(tags.map(tag => [tag.tag, tag]));
      el('tag-grid').replaceChildren(...tagLayout.map(([name, bearing]) => {
        const item = document.createElement('div');
        const tag = byName[name];
        item.className = `tag${tag ? ' ready' : ''}`;
        item.innerHTML = `<span class="tag-angle">${bearing}°</span><strong>${name}</strong><span class="tag-status">${tag ? `last sample ${tag.age_s}s` : 'No samples'}</span>`;
        return item;
      }));
      el('ready-count').textContent = `${tags.length} / 9 ready`;
      el('start-run').disabled = tags.length === 0;
      el('start-run').className = tags.length === 9 ? 'primary' : 'warning';
      el('start-run').textContent = tags.length === 9 ? 'Start acquisition' : `Start partial run (${tags.length}/9)`;

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
      const minimum = Math.min(...participating.map(tag => counts[tag] || 0));
      const percent = Math.min(100, Math.floor(minimum * 100 / active.target_samples));
      el('active-label').textContent = `${active.distance_m} m · ${active.rotation_deg}°`;
      el('run-progress').style.width = `${percent}%`;
      el('run-count').textContent = `${minimum} / ${active.target_samples} minimum samples`;
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
      const missing = expectedTags.filter(tag => !readyTags.includes(tag));
      if (missing.length && !await askConfirmation({
        title: 'Start partial run?',
        message: `Missing tags: ${missing.join(', ')}. The run will use ${readyTags.length} of 9 tags.`,
        confirmLabel: 'Start partial run',
        tone: 'warning'
      })) return;
      try { await post('/api/run/start', {distance_m: selectedDistance, rotation_deg: selectedRotation}); await refresh(); }
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


def parse_sample_time(value):
    try:
        return time.mktime(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S"))
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
        if auto_start:
            self.start_monitor()

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
            if row["age_s"] <= 5 and tag in {item["tag"] for item in TAG_LAYOUT}:
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
        paths = [path for path in self.log_dir.glob("pdoa_*.csv") if path.stat().st_mtime >= started_at - 2]
        known_tags = {item["tag"] for item in TAG_LAYOUT}
        return [
            row for row in self._read_rows(sorted(paths))
            if row.get("tag") in known_tags and parse_sample_time(row.get("time")) >= started_at
        ]

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

    def start_run(self, distance_m, rotation_deg):
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
            ready_tags = sorted(row["tag"] for row in self.samples()["tags"])
            if not ready_tags:
                raise ValueError("At least one tag must be ready before starting")
            expected_tags = [item["tag"] for item in TAG_LAYOUT]
            missing_tags = [tag for tag in expected_tags if tag not in ready_tags]
            key = f"{distance_m}:{rotation_deg}"
            attempt = state["conditions"][key]["attempts"] + 1
            state["conditions"][key] = {"status": "active", "attempts": attempt}
            state["active_run"] = {
                "distance_m": distance_m,
                "rotation_deg": rotation_deg,
                "attempt": attempt,
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "started_epoch": time.time(),
                "target_samples": state["target_samples"],
                "timeout_s": RUN_TIMEOUT_S,
                "participating_tags": ready_tags,
                "missing_tags": missing_tags,
                "counts": {item["tag"]: 0 for item in TAG_LAYOUT},
            }
            self._persist_experiment(state)
            return state["active_run"]

    def _finish_run(self, state, status, rows=None):
        active = state["active_run"]
        rows = self._run_rows(active) if rows is None else rows
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
                counts = self._counts(rows)
                state["active_run"]["counts"] = counts
                participating = state["active_run"]["participating_tags"]
                target_reached = min(counts[tag] for tag in participating) >= state["active_run"]["target_samples"]
                timed_out = time.time() - state["active_run"]["started_epoch"] >= state["active_run"]["timeout_s"]
                if target_reached or timed_out:
                    run_status = "complete" if target_reached and not state["active_run"]["missing_tags"] else "partial"
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
            elif path == "/api/samples":
                self._json(app.samples())
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
                    self._json(app.start_run(body.get("distance_m"), body.get("rotation_deg")), 201)
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
