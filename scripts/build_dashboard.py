"""Sinh dashboard HTML 6 panel từ data/logs.jsonl (không cần dependency mới).

Dùng `config/dashboard.yaml` làm nguồn contract (panel, unit, threshold, time range).
Mở file HTML bằng trình duyệt để chụp evidence 11.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from app.cli import configure_utf8_stdio  # noqa: E402
from app.metrics import percentile  # noqa: E402

LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
OUT_PATH = REPO_ROOT / "submission" / "dashboard.html"


def load_records() -> list[dict]:
    if not LOG_PATH.exists():
        raise SystemExit(f"Không tìm thấy {LOG_PATH}. Chạy API và load test trước.")
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not records:
        raise SystemExit("data/logs.jsonl không có dòng JSON hợp lệ.")
    return records


def window_bounds(records: list[dict], minutes: int) -> tuple[str, str]:
    timestamps = [
        datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        for rec in records
        if isinstance(rec.get("ts"), str)
    ]
    end = max(timestamps)
    return (end - timedelta(minutes=minutes)).isoformat(), end.isoformat()


def summarize(records: list[dict], window_start: str) -> dict:
    received, failed, error_types, success, fail_tool = 0, 0, Counter(), 0, 0
    latencies, ttfts, costs, tokens_in, tokens_out, quality = [], [], [], [], [], []
    buckets: dict[str, dict[str, list]] = {}

    for rec in records:
        win = rec["ts"] >= window_start
        if rec.get("event") == "request_received":
            received += 1
            if win:
                buckets.setdefault(rec["ts"][:16], {"count": 0})["count"] += 1
        elif rec.get("event") == "request_failed":
            failed += 1
            error_types[rec.get("error_type", "unknown")] += 1
            if win:
                bucket = buckets.setdefault(rec["ts"][:16], {"count": 0, "failed": 0})
                bucket["failed"] = bucket.get("failed", 0) + 1
        elif rec.get("event") == "response_sent" and win:
            buckets.setdefault(rec["ts"][:16], {"count": 0, "failed": 0})
            bucket = buckets[rec["ts"][:16]]
            bucket.setdefault("lat", []).append(rec.get("latency_ms", 0) or 0)
            bucket.setdefault("ttft", []).append(rec.get("ttft_ms", 0) or 0)
            bucket.setdefault("cost", []).append(rec.get("cost_usd", 0) or 0)
            bucket.setdefault("tin", []).append(rec.get("tokens_in", 0) or 0)
            bucket.setdefault("tout", []).append(rec.get("tokens_out", 0) or 0)
            bucket.setdefault("quality", []).append(rec.get("quality_score", 0) or 0)

            latencies.append(rec.get("latency_ms", 0) or 0)
            ttfts.append(rec.get("ttft_ms", 0) or 0)
            costs.append(rec.get("cost_usd", 0) or 0)
            tokens_in.append(rec.get("tokens_in", 0) or 0)
            tokens_out.append(rec.get("tokens_out", 0) or 0)
            quality.append(rec.get("quality_score", 0) or 0)
            if rec.get("tool_success") is True:
                success += 1
            elif rec.get("tool_success") is False:
                fail_tool += 1

    series = []
    minutes = 0.0
    for minute in sorted(buckets):
        bucket = buckets[minute]
        minutes += 1.0
        series.append(
            {
                "minute": minute[-5:],
                "count": bucket.get("count", 0),
                "failed": bucket.get("failed", 0),
                "lat_p95": percentile(bucket.get("lat", []), 95),
                "lat_p50": percentile(bucket.get("lat", []), 50),
                "ttft_p95": percentile(bucket.get("ttft", []), 95),
                "cost": round(sum(bucket.get("cost", [])), 6),
                "tokens_in": sum(bucket.get("tin", [])),
                "tokens_out": sum(bucket.get("tout", [])),
                "quality": round(sum(bucket.get("quality", [])) / len(bucket["quality"]), 2)
                if bucket.get("quality")
                else 0,
                "error_rate": round(
                    bucket.get("failed", 0) / max(bucket.get("count", 0), 1) * 100, 2
                ),
            }
        )

    retrieval_denominator = success + fail_tool
    return {
        "traffic_total": received,
        "traffic_rate": round(received / max(minutes, 1.0), 1),
        "latency_p50": percentile(latencies, 50),
        "latency_p95": percentile(latencies, 95),
        "latency_p99": percentile(latencies, 99),
        "ttft_p95": percentile(ttfts, 95),
        "error_rate": round(failed / max(received, 1) * 100, 2),
        "error_breakdown": dict(error_types),
        "retrieval_success": round(success / max(retrieval_denominator, 1) * 100, 1),
        "cost_total": round(sum(costs), 6),
        "tokens_in_total": sum(tokens_in),
        "tokens_out_total": sum(tokens_out),
        "quality_avg": round(sum(quality) / len(quality), 2) if quality else 0,
        "series": series,
    }


def main() -> None:
    configure_utf8_stdio()
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["dashboard"]
    panel_meta = {panel["id"]: panel for panel in config["panels"]}

    records = load_records()
    window_start, window_end = window_bounds(records, config["time_range_minutes"])
    stats = summarize(records, window_start)

    payload = {
        "title": config["title"],
        "time_range_minutes": config["time_range_minutes"],
        "window_start": window_start,
        "window_end": window_end,
        "panels": [
            {
                "id": pid,
                "title": panel_meta[pid]["title"],
                "unit": panel_meta[pid]["unit"],
                "threshold": panel_meta[pid]["threshold"],
                **{key: stats[key] for key in panel_stats[pid]},
            }
            for pid in ("latency", "traffic", "errors", "cost", "tokens", "quality")
        ]
        + [{"id": "__series__", "series": stats["series"]}],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(HTML_TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False)), encoding="utf-8")
    print(f"Đã ghi {OUT_PATH} — mở bằng trình duyệt để chụp evidence 11.")
    print(f"Time range: {window_start} -> {window_end} (UTC)")


panel_stats = {
    "latency": ("latency_p50", "latency_p95", "latency_p99", "ttft_p95"),
    "traffic": ("traffic_total", "traffic_rate"),
    "errors": ("error_rate", "error_breakdown", "retrieval_success"),
    "cost": ("cost_total",),
    "tokens": ("tokens_in_total", "tokens_out_total"),
    "quality": ("quality_avg",),
}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>K4-L3B Day 13 Monitoring &amp; LLMOps</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 16px; background: #f6f7f9; color: #1c2733; }
  h1 { font-size: 18px; margin: 0 0 2px; }
  .meta { color: #5b6b7c; font-size: 12px; margin-bottom: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px; }
  .panel { background: #fff; border: 1px solid #dde3ea; border-radius: 8px; padding: 10px 12px; }
  .panel h2 { font-size: 13px; margin: 0 0 4px; }
  .unit { color: #5b6b7c; font-size: 11px; font-weight: normal; }
  .values { font-size: 12px; margin: 2px 0 6px; }
  .values b { font-size: 14px; }
  .threshold { font-size: 11px; color: #0460a9; }
  svg { width: 100%; height: 110px; }
  .line { fill: none; stroke: #0460a9; stroke-width: 2; }
  .line2 { fill: none; stroke: #d97706; stroke-width: 2; }
  .bar { fill: #7ea7cd; }
  .target { stroke: #c2410c; stroke-width: 1.5; stroke-dasharray: 4 3; }
  .axis { stroke: #cfd8e2; stroke-width: 1; }
  text { font-size: 9px; fill: #5b6b7c; }
</style>
</head>
<body>
<h1 id="title"></h1>
<div class="meta" id="meta"></div>
<div class="grid" id="grid"></div>
<script>
const DATA = __DATA__;
document.getElementById('title').textContent = DATA.title;
document.getElementById('meta').textContent =
  `Time range: ${DATA.time_range_minutes} phút (${DATA.window_start} -> ${DATA.window_end} UTC). Nguồn: data/logs.jsonl. Refresh: chạy lại scripts/build_dashboard.py.`;
const SERIES = DATA.panels.pop();
const W = 320, H = 90, PAD = 24;

function chart(values, target, scale2) {
  const n = values.length;
  if (!n) return '<div class="values"><i>Chưa có dữ liệu trong cửa sổ.</i></div>';
  const max = Math.max(...values, ...(target != null && target > 0 ? [target] : []), 1);
  const min = 0;
  const x = i => PAD + (n === 1 ? 0 : i * (W - PAD) / (n - 1));
  const y = v => H - 6 - (v - min) / (max - min) * (H - 12);
  const pts = values.map((v, i) => x(i) + ',' + y(v)).join(' ');
  let s = `<svg viewBox="0 0 ${W} ${H}">` +
    `<line class="axis" x1="${PAD}" y1="${H - 6}" x2="${W - 8}" y2="${H - 6}"/>` +
    `<line class="axis" x1="${PAD}" y1="${H - 6}" x2="${PAD}" y2="${4}"/>`;
  if (target != null && target >= min && target <= max) {
    s += `<line class="target" x1="${PAD}" y1="${y(target)}" x2="${W - 8}" y2="${y(target)}"/>`;
    s += `<text x="${W - 76}" y="${Math.max(y(target) - 3, 8)}">threshold ${target}</text>`;
  }
  s += `<polyline class="line" points="${pts}"/>`;
  if (scale2) s += `<polyline class="line2" points="${scale2.map((v, i) => x(i) + ',' + y(v)).join(' ')}"/>`;
  s += `<text x="${PAD}" y="${H - 8}">${SERIES.series[0] ? SERIES.series[0].minute : ''}</text>` +
       `<text x="${W - 60}" y="${H - 8}">${SERIES.series[n - 1] ? SERIES.series[n - 1].minute : ''}</text></svg>`;
  return s;
}

function barChart(values, target) {
  const n = values.length;
  if (!n) return '<div class="values"><i>Chưa có dữ liệu trong cửa sổ.</i></div>';
  const max = Math.max(...values, target ?? 1, 1);
  const bw = (W - PAD - 8) / n;
  let s = `<svg viewBox="0 0 ${W} ${H}">` +
    `<line class="axis" x1="${PAD}" y1="${H - 6}" x2="${W - 8}" y2="${H - 6}"/>`;
  values.forEach((v, i) => {
    const h = v / max * (H - 12);
    s += `<rect class="bar" x="${PAD + i * bw + 1}" y="${H - 6 - h}" width="${Math.max(bw - 2, 1)}" height="${h}"/>`;
  });
  s += `<text x="${W - 76}" y="${10}">max ${max}</text></svg>`;
  return s;
}

const seriesOf = pick => SERIES.series.map(row => row[pick]);
const grid = document.getElementById('grid');
for (const p of DATA.panels) {
  const t = p.threshold;
  const th = `${t.aggregation} ${t.operator} ${t.value} (${p.unit})`;
  let values, svg, labels;
  if (p.id === 'latency') {
    labels = `P50 <b>${p.latency_p50}ms</b> · P95 <b>${p.latency_p95}ms</b> · P99 <b>${p.latency_p99}ms</b> · TTFT P95 <b>${p.ttft_p95}ms</b>`;
    values = 'lat_p95';
    svg = chart(seriesOf('lat_p95'), t.value, seriesOf('lat_p50'));
  } else if (p.id === 'traffic') {
    labels = `Tổng <b>${p.traffic_total}</b> · rate <b>${p.traffic_rate}/${p.unit.replace('_', '/')}</b>`;
    values = 'count';
    svg = barChart(seriesOf('count'), t.value);
  } else if (p.id === 'errors') {
    const bd = Object.entries(p.error_breakdown).map(([k, v]) => `${k}: ${v}`).join(' · ') || '-';
    labels = `Error rate <b>${p.error_rate}%</b> · Retrieval success <b>${p.retrieval_success}%</b><br><span style="color:#5b6b7c">Breakdown: ${bd}</span>`;
    values = 'error_rate';
    svg = chart(seriesOf('error_rate'), t.value);
  } else if (p.id === 'cost') {
    labels = `Tổng <b>$${p.cost_total}</b>`;
    values = 'cost';
    svg = chart(seriesOf('cost'), t.value);
  } else if (p.id === 'tokens') {
    labels = `Input <b>${p.tokens_in_total}</b> · Output <b>${p.tokens_out_total}</b>`;
    values = 'tokens_in';
    svg = chart(seriesOf('tokens_in'), t.value, seriesOf('tokens_out'));
  } else {
    labels = `Quality proxy <b>${p.quality_avg}</b> (/1)`;
    values = 'quality';
    svg = chart(seriesOf('quality'), t.value);
  }
  const div = document.createElement('div');
  div.className = 'panel';
  div.innerHTML = `<h2>${p.title} <span class="unit">(${p.unit})</span></h2>
    <div class="values">${labels}</div>${svg}
    <div class="threshold">Threshold: ${th}</div>`;
  grid.appendChild(div);
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()