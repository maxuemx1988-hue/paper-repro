#!/usr/bin/env python3
"""Multimodal figure reading through an OpenAI-compatible endpoint (default: Kimi on 12ai).

Why a separate script instead of "just look at the image": the crop/axis audit that
`check_visual_crop.py` enforces needs machine-readable fields (subfigure id, axis label,
unit, limits, scale).  A vision model can fill those, but a model reading is *evidence*,
not truth: this script therefore

  * records `model_requested` / `model_used` and the reason for any fallback,
  * hash-binds the image actually sent and the raw response it got,
  * lets a human override any field and marks which fields came from the override,
  * refuses to invent values: empty/implausible limits abort instead of being guessed.

Subcommands
    probe    list which candidate models answer at the configured endpoint
    describe read one image and print/write structured axis metadata
    audit    write/merge `<crop>.visual_audit.json` consumed by check_visual_crop.py
    judge    compare a paper crop against a reproduced figure (evidence for §4 对比)

Endpoint / model / key resolution (first hit wins)
    --base-url, --model, --api-key
    PAPER_REPRO_VISION_BASE_URL / PAPER_REPRO_VISION_MODELS / PAPER_REPRO_VISION_API_KEY
    OPENAI_BASE_URL / OPENAI_API_KEY
    ~/.pi/agent/models.json (provider whose baseUrl matches the host, e.g. "12ai")

Examples
    python3 scripts/vision.py probe
    python3 scripts/vision.py describe crops/fig3b.png -o crops/fig3b.vision.json
    python3 scripts/vision.py audit . data/ground_truth/fig3b_crop.png \
        --pdf paper/paper.pdf --page 5 --bbox "120,80,860,600" --subfigure "Fig3(b)" \
        --xlabel "photon energy" --xunit eV --xlims 0,8 --ylabel "G" --yunit "e^2/h" --ylims 0,2
    python3 scripts/vision.py judge . fig3b \
        --paper data/ground_truth/fig3b_crop.png --mine figures/mine/fig3b.png
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from common import read_json, require, sha256, within

DEFAULT_BASE = "https://api.12ai.org/v1"
DEFAULT_MODELS = ("kimi-k3", "kimi-k2.6")   # probe first; kimi-k2.6 is 404 in some groups
PROMPT_VERSION = "figure-read-v1"
FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.M)
# "not available for this group" / "no available channel" => try the next model
UNAVAILABLE = ("not available for this group", "no available channel", "model_not_found",
               "does not exist", "invalid model")


# --------------------------------------------------------------------------- config

def _pi_provider_key(host: str):
    """Return (base_url, api_key) for the first pi provider whose host matches."""
    path = Path.home() / ".pi/agent/models.json"
    if not path.is_file():
        return None, None
    try:
        doc = read_json(path)
    except Exception:
        return None, None
    for _, provider in (doc.get("providers") or {}).items():
        base = str(provider.get("baseUrl") or "")
        if not base:
            continue
        provider_host = re.sub(r"^https?://", "", base).split("/")[0]
        if provider_host and provider_host in host:
            key = provider.get("apiKey")
            if isinstance(key, str) and key.strip():
                return base, key.strip()
    return None, None


def resolve(args):
    host = args.base_url or os.environ.get("PAPER_REPRO_VISION_BASE_URL") \
        or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE
    host = host.rstrip("/")
    key = args.api_key or os.environ.get("PAPER_REPRO_VISION_API_KEY") \
        or os.environ.get("OPENAI_API_KEY")
    if not key:
        _, key = _pi_provider_key(host)
    require(bool(key), "no API key: pass --api-key, set PAPER_REPRO_VISION_API_KEY/OPENAI_API_KEY, "
                       "or configure a pi provider for this host in ~/.pi/agent/models.json")
    models = list(args.model or ())
    if not models:
        env = os.environ.get("PAPER_REPRO_VISION_MODELS")
        models = [m.strip() for m in env.split(",") if m.strip()] if env else list(DEFAULT_MODELS)
    return host, key, models


def _mime(path: Path) -> str:
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "bmp": "image/bmp", "gif": "image/gif"}.get(
                path.suffix.lower().lstrip("."), "image/png")


def encode(path: Path, max_side: int | None):
    """Return (data_url, sent_sha256, note). Shrinks huge images to bound token cost.

    A pixel cap alone is not enough: a 760x604 PNG of a vector plot can weigh ~700 kB
    and some OpenAI-compatible gateways silently drop the image from such a request
    (`image_tokens: 0`, empty content).  So we also enforce a payload budget and fall
    back to JPEG quality 88, then to a smaller size, until the payload fits.
    """
    # bytes of the *decoded* image payload.  Measured on the 12ai gateway (Nov 2026):
    # a 600x477 PNG (82 kB) is silently dropped (`image_tokens: 0`, empty content) while
    # 500x397 (65 kB) and any JPEG below ~50 kB go through.  Keep a margin below that.
    PAYLOAD_LIMIT = 56_000

    def data_url(payload: bytes, mime: str) -> str:
        return f"data:{mime};base64," + base64.b64encode(payload).decode()

    raw = path.read_bytes()
    if not max_side and len(raw) <= PAYLOAD_LIMIT:
        return data_url(raw, _mime(path)), sha256(path), None
    try:
        from PIL import Image
    except ImportError:
        return data_url(raw, _mime(path)), sha256(path), "Pillow 不可用，按原图发送"
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        original = im.size
        side = max_side or max(original)
        note = None
        while True:
            scale = min(1.0, side / max(original))
            resized = im.convert("RGB")
            if scale < 1.0:
                resized = resized.resize((max(1, round(original[0] * scale)),
                                          max(1, round(original[1] * scale))))
            for fmt, mime, kwargs in (("PNG", "image/png", {}),
                                      ("JPEG", "image/jpeg", {"quality": 90}),
                                      ("JPEG", "image/jpeg", {"quality": 75})):
                buf = io.BytesIO()
                resized.save(buf, format=fmt, **kwargs)
                payload = buf.getvalue()
                if len(payload) <= PAYLOAD_LIMIT:
                    if resized.size != original or fmt != "PNG":
                        note = (f"发送前压缩原图 {original} -> {resized.size} {fmt}"
                                f"（{len(raw) // 1024} kB -> {len(payload) // 1024} kB）；"
                                "坐标类结论必须用原图像素重新核对")
                    return data_url(payload, mime), hashlib.sha256(payload).hexdigest(), note
            if side <= 200:
                raise SystemExit(f"[ERR] {path} 压缩到 {side}px 仍超过请求体预算，无法可靠送图")
            side = int(side * 0.7)


# --------------------------------------------------------------------------- transport

def post(host, key, payload, timeout):
    request = urllib.request.Request(
        host + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from None


def _cache_path():
    root = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(root) / "paper-repro" / "vision_hosts.json"


def _cache_read():
    try:
        return read_json(_cache_path()) or {}
    except Exception:
        return {}


def _cache_mark(host, model, status, detail=""):
    path = _cache_path()
    doc = _cache_read()
    doc[f"{host}|{model}"] = {"status": status, "detail": detail[:200],
                              "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass                      # cache is an optimisation, never fatal


def _image_tokens(reply):
    usage = reply.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    value = details.get("image_tokens")
    return -1 if value is None else int(value)


def call(host, key, models, content, timeout, max_tokens, temperature=0.0):
    """Try each model in order; return (model_used, text, trace)."""
    sends_image = any(isinstance(part, dict) and part.get("type") == "image_url"
                      for part in content) if isinstance(content, list) else False
    trace = []
    cache = _cache_read()
    # models this endpoint already refused go last: one wasted round trip per host, not per call
    ranked = sorted(models, key=lambda m: "unavailable" ==
                    (cache.get(f"{host}|{m}") or {}).get("status"))
    for model in ranked:
        payload = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": content}]}
        try:
            reply = post(host, key, payload, timeout)
        except RuntimeError as exc:
            message = str(exc)
            trace.append({"model": model, "status": "error", "detail": message[:300]})
            if any(token in message.lower() for token in UNAVAILABLE):
                _cache_mark(host, model, "unavailable", message)   # this group has no such model
                continue          # try the next one
            continue
        choice = (reply.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content")
        if isinstance(text, list):
            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
        if sends_image and _image_tokens(reply) == 0:
            # the gateway accepted the JSON but dropped the image: any text would be a
            # reading of something the model never saw, so this is not usable evidence
            trace.append({"model": model, "status": "no_image",
                          "detail": "image_tokens=0: 网关把图丢了（请求体过大时常见），已尝试缩小重发"})
            continue
        if not text or not str(text).strip():
            trace.append({"model": model, "status": "empty", "detail": "no content in response"})
            continue
        trace.append({"model": model, "status": "ok"})
        _cache_mark(host, model, "ok")
        return model, str(text), trace
    raise SystemExit("[ERR] 没有可用模型：\n" + json.dumps(trace, ensure_ascii=False, indent=2)
                     + "\n提示：`python3 scripts/vision.py probe` 查看哪些模型可用，"
                       "或在 ~/.pi/agent/models.json 里换一个能开图的分组")


def parse_json(text, what):
    body = FENCE.sub("", str(text).strip())
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    start, end = body.find("{"), body.rfind("}")
    require(start >= 0 and end > start, f"{what}: 模型没有返回 JSON 对象；原文前 300 字：{body[:300]}")
    try:
        return json.loads(body[start:end + 1])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[ERR] {what}: 模型返回的 JSON 无法解析（{exc}）；原文前 300 字：{body[:300]}")


# --------------------------------------------------------------------------- prompts

SCHEMA = """Return ONLY one JSON object, no prose, with exactly these keys:
{
  "subfigure_id": "<panel label such as 'Fig3(b)'; use '' if not printed inside the image>",
  "panel_kind": "curve|scatter|heatmap|bar|table|schematic|other",
  "xaxis": {"label": "<axis title as printed>", "unit": "<unit as printed, '1' if dimensionless>",
            "limits": [<numeric lower>, <numeric upper>], "scale": "linear|log",
            "tick_labels": ["<printed tick text, left to right>"]},
  "yaxis": {"label": "...", "unit": "...", "limits": [<lo>, <hi>], "scale": "linear|log",
            "tick_labels": ["<bottom to top>"]},
  "n_curves": <integer>,
  "curve_colors": ["<#rrggbb of each plotted line, in legend order>"],
  "legend_labels": ["<legend entry as printed>"],
  "caption_text": "<figure caption or in-panel text, verbatim, '' if none>",
  "values_printed": ["<any numeric annotation printed inside the panel, verbatim>"],
  "digitizable": true|false,
  "uncertainty_notes": "<what you could not read, blur, overlapping curves, axis breaks>",
  "confidence": "high|medium|low"
}
Rules: read numbers from the printed tick labels only; never extrapolate or invent a limit.
If a field is unreadable, use null (not a guess) and say so in uncertainty_notes."""


def read_prompt(hint=None):
    head = (f"You are auditing a scientific figure crop to be used as quantitative ground truth.\n"
            f"Reported panel id by the caller: {hint}\n" if hint else
            "You are auditing a scientific figure crop to be used as quantitative ground truth.\n")
    return head + SCHEMA


def judge_prompt(tid):
    return (f"Image 1 is the ORIGINAL crop from the paper for target '{tid}'. "
            "Image 2 is an INDEPENDENT reproduction computed by us.\n"
            "Compare them as a physicist, not as an artist. Return ONLY one JSON object:\n"
            '{"verdict":"agree|partial|disagree","axis_units":"agree|mismatch|unreadable",'
            '"axis_ranges":"agree|mismatch|unreadable","shape":"agree|partial|mismatch",'
            '"magnitude":"agree|partial|mismatch","features":["<peak/gap/plateau that matches or not>"],'
            '"discrepancies":["<concrete difference worth investigating>"],'
            '"notes":"<what a human must re-check>","confidence":"high|medium|low"}\n'
            "Say 'mismatch' when a physical scale (per-unit vs per-supercell, eV vs meV, "
            "e^2/h vs mS) could differ, and name it in discrepancies.")


# --------------------------------------------------------------------------- subcommands

def probe(args):
    host, key, models = resolve(args)
    print(f"[info] endpoint {host}; key {'*' * 6}{key[-4:]}; candidates {models}")
    ok = []
    for model in models:
        payload = {"model": model, "max_tokens": 16, "temperature": 0,
                   "messages": [{"role": "user", "content": "reply with: ok"}]}
        try:
            post(host, key, payload, args.timeout)
            ok.append(model)
            print(f"  OK       {model}")
        except RuntimeError as exc:
            print(f"  UNAVAIL  {model}: {str(exc)[:160]}")
    require(ok, "候选模型在该 endpoint/分组下都不可用；换 --model 或换 key")
    print(f"[PASS] usable: {ok}")
    return 0


def describe(args):
    host, key, models = resolve(args)
    image = Path(args.image).expanduser().resolve()
    require(image.is_file(), f"missing image: {image}")
    data_url, sent_sha, note = encode(image, args.max_side)
    model, text, trace = call(host, key, models,
                              [{"type": "text", "text": read_prompt(args.subfigure)},
                               {"type": "image_url", "image_url": {"url": data_url}}],
                              args.timeout, args.max_tokens)
    payload = parse_json(text, "describe")
    out = {
        "schema_version": 1, "prompt_version": PROMPT_VERSION,
        "image": {"file": str(image), "sha256": sha256(image)},
        "sent": {"sha256": sent_sha, "note": note},
        "model_requested": models, "model_used": model, "trace": trace,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reading": payload, "raw_response": text,
    }
    target = Path(args.out).expanduser() if args.out else image.with_suffix(".vision.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"[vision] {target}")
    return 0


def _axis(value, name, overrides, key):
    """Merge model reading with CLI override; refuse to invent a bound."""
    source = "model"
    label = overrides.get(f"{key}label") or (value or {}).get("label")
    unit = overrides.get(f"{key}unit") or (value or {}).get("unit")
    scale = overrides.get(f"{key}scale") or (value or {}).get("scale") or "linear"
    limits = overrides.get(f"{key}lims") or (value or {}).get("limits")
    if overrides.get(f"{key}label") or overrides.get(f"{key}unit") \
            or overrides.get(f"{key}lims") or overrides.get(f"{key}scale"):
        source = "model+override"
    require(isinstance(label, str) and label.strip(),
            f"{name} label 未读到：用 --{key}label 覆盖（禁止猜测）")
    require(isinstance(unit, str) and unit.strip(),
            f"{name} unit 未读到：用 --{key}unit 覆盖（无量纲写 1）")
    require(scale in ("linear", "log"), f"{name} scale 必须是 linear/log")
    require(isinstance(limits, (list, tuple)) and len(limits) == 2,
            f"{name} limits 未读到：用 --{key}lims lo,hi 覆盖（禁止猜测）")
    try:
        lo, hi = float(limits[0]), float(limits[1])
    except (TypeError, ValueError):
        raise SystemExit(f"[ERR] {name} limits 不是数值：{limits!r}；请用 --{key}lims 覆盖")
    require(lo < hi, f"{name} limits 必须递增（得到 {lo}, {hi}）")
    require(scale != "log" or lo > 0, f"{name} 对数轴下限必须为正")
    return {"label": label.strip(), "unit": unit.strip(), "limits": [lo, hi],
            "scale": scale, "source": source}


def audit(args):
    root = Path(args.root).expanduser().resolve()
    crop = within(root, args.crop)
    require(crop.is_file(), f"missing crop: {args.crop}")
    pdf = within(root, args.pdf)
    require(pdf.is_file(), f"missing pdf: {args.pdf}")
    host, key, models = resolve(args)

    overrides = {}
    for name in ("xlabel", "xunit", "xlims", "xscale", "ylabel", "yunit", "ylims", "yscale"):
        value = getattr(args, name, None)
        if value:
            overrides[name] = value
    parsed = dict(overrides)
    for name in ("xlims", "ylims"):
        if name in parsed:
            parts = str(parsed[name]).split(",")
            require(len(parts) == 2, f"--{name} 需要 lo,hi")
            parsed[name] = [float(parts[0]), float(parts[1])]

    data_url, sent_sha, note = encode(crop, args.max_side)
    model, text, trace = call(host, key, models,
                              [{"type": "text", "text": read_prompt(args.subfigure)},
                               {"type": "image_url", "image_url": {"url": data_url}}],
                              args.timeout, args.max_tokens)
    reading = parse_json(text, "audit")

    subfigure = args.subfigure or (reading.get("subfigure_id") or "").strip()
    require(bool(subfigure), "subfigure id 未读到：用 --subfigure 覆盖")
    bbox = [float(v) for v in str(args.bbox).split(",")] if args.bbox else None
    require(bbox is not None and len(bbox) == 4, "必须用 --bbox 给出 PDF 坐标框 x0,y0,x1,y1")

    raw = crop.with_suffix(".vision.json")
    raw.write_text(json.dumps({
        "schema_version": 1, "prompt_version": PROMPT_VERSION,
        "image": {"file": args.crop, "sha256": sha256(crop)},
        "sent": {"sha256": sent_sha, "note": note},
        "model_requested": models, "model_used": model, "trace": trace,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reading": reading, "raw_response": text}, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {
        "image": {"file": args.crop, "sha256": sha256(crop)},
        "pdf": {"file": args.pdf, "sha256": sha256(pdf)},
        "page": args.page,
        "bbox_pdf": bbox,
        "subfigure_id": subfigure,
        "xaxis": _axis(reading.get("xaxis"), "xaxis", parsed, "x"),
        "yaxis": _axis(reading.get("yaxis"), "yaxis", parsed, "y"),
        "review": {
            "method": "model",
            "reviewer": model,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notes": (reading.get("uncertainty_notes") or "").strip()
                     or "模型读数，未经人工逐项复核",
        },
        "vision": {
            "model_requested": models, "model_used": model,
            "raw": {"file": str(raw.relative_to(root)), "sha256": sha256(raw)},
            "panel_kind": reading.get("panel_kind"),
            "n_curves": reading.get("n_curves"),
            "curve_colors": reading.get("curve_colors") or [],
            "legend_labels": reading.get("legend_labels") or [],
            "caption_text": reading.get("caption_text") or "",
            "values_printed": reading.get("values_printed") or [],
            "digitizable": reading.get("digitizable"),
            "confidence": reading.get("confidence"),
            "uncertainty_notes": reading.get("uncertainty_notes"),
            "fallback_trace": [t for t in trace if t.get("status") != "ok"],
            "sent_note": note,
        },
    }
    out = crop.with_suffix(".visual_audit.json")
    if out.is_file() and not args.force:
        raise SystemExit(f"[ERR] {out} 已存在；确认覆盖请加 --force（先备份人工复核结论）")
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[vision] model={model} subfigure={subfigure}")
    for key in ("xaxis", "yaxis"):
        axis = meta[key]
        print(f"         {key}: {axis['label']} [{axis['unit']}] {axis['limits']} {axis['scale']} ({axis['source']})")
    print(f"[vision] {out}")
    print("[note] 模型读数只是证据：坐标与量程必须再经 check_visual_crop.py + 人工/read 复核")
    return 0


def judge(args):
    root = Path(args.root).expanduser().resolve()
    paper = within(root, args.paper)
    mine = within(root, args.mine)
    for path in (paper, mine):
        require(path.is_file(), f"missing image: {path}")
    host, key, models = resolve(args)
    paper_url, paper_sha, paper_note = encode(paper, args.max_side)
    mine_url, mine_sha, mine_note = encode(mine, args.max_side)
    model, text, trace = call(host, key, models,
                              [{"type": "text", "text": judge_prompt(args.tid)},
                               {"type": "text", "text": "Image 1 (paper original):"},
                               {"type": "image_url", "image_url": {"url": paper_url}},
                               {"type": "text", "text": "Image 2 (our reproduction):"},
                               {"type": "image_url", "image_url": {"url": mine_url}}],
                              args.timeout, args.max_tokens)
    verdict = parse_json(text, "judge")
    record = {
        "schema_version": 1, "prompt_version": PROMPT_VERSION, "target": args.tid,
        "paper": {"file": args.paper, "sha256": sha256(paper)},
        "mine": {"file": args.mine, "sha256": sha256(mine)},
        "sent": {"paper": paper_sha, "mine": mine_sha,
                 "note": paper_note or mine_note},
        "model_requested": models, "model_used": model, "trace": trace,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "judgement": verdict, "raw_response": text,
    }
    out = within(root, args.out) if args.out else Path(root) / "figures/compare" / f"{args.tid}.vision_judge.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    print(f"[vision] {out}")
    print("[note] 视觉判定是证据，不替代 check_loss / check_figure_side_by_side；不一致必须写进 REPORT.md §3")
    if verdict.get("verdict") == "disagree":
        print("[warn] 模型判定不一致：先查量纲/量级，再决定是调模型还是调代码（禁止直接拟合论文图）")
    return 0


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, image=True):
        p.add_argument("--base-url", default=None, help=f"OpenAI 兼容 base url，默认 {DEFAULT_BASE}")
        p.add_argument("--model", action="append", default=None,
                       help="候选模型，可重复；默认 kimi-k2.6,kimi-k3 依次回退")
        p.add_argument("--api-key", default=None, help="默认读 PAPER_REPRO_VISION_API_KEY / OPENAI_API_KEY / pi models.json")
        p.add_argument("--timeout", type=float, default=180.0)
        p.add_argument("--max-tokens", type=int, default=1200)
        p.add_argument("--max-side", type=int, default=1600,
                       help="发送前把长边缩到不超过该像素（0=原图）；坐标类结论请用原图复核")

    p_probe = sub.add_parser("probe", help="检查候选模型在该 endpoint 下是否可用")
    common(p_probe)
    p_probe.set_defaults(func=probe)

    p_desc = sub.add_parser("describe", help="读一张图，输出结构化轴信息 JSON")
    p_desc.add_argument("image")
    p_desc.add_argument("-o", "--out", default=None)
    p_desc.add_argument("--subfigure", default=None)
    common(p_desc)
    p_desc.set_defaults(func=describe)

    p_audit = sub.add_parser("audit", help="写 <crop>.visual_audit.json（check_visual_crop.py 消费）")
    p_audit.add_argument("root")
    p_audit.add_argument("crop")
    p_audit.add_argument("--pdf", required=True)
    p_audit.add_argument("--page", type=int, required=True)
    p_audit.add_argument("--bbox", required=True, help="PDF 坐标框 x0,y0,x1,y1")
    p_audit.add_argument("--subfigure", default=None, help="论文面板 id，如 Fig3(b)")
    for key in ("xlabel", "xunit", "xlims", "xscale", "ylabel", "yunit", "ylims", "yscale"):
        p_audit.add_argument(f"--{key}", default=None, help="覆盖模型读数（覆盖来源会被记录）")
    p_audit.add_argument("--force", action="store_true")
    common(p_audit)
    p_audit.set_defaults(func=audit)

    p_judge = sub.add_parser("judge", help="论文图 vs 复现图 的视觉对照证据")
    p_judge.add_argument("root")
    p_judge.add_argument("tid")
    p_judge.add_argument("--paper", required=True)
    p_judge.add_argument("--mine", required=True)
    p_judge.add_argument("-o", "--out", default=None)
    common(p_judge)
    p_judge.set_defaults(func=judge)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"[INCOMPLETE] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
