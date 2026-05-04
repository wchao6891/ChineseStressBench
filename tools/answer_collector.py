#!/usr/bin/env python3
"""Local benchmark answer collector.

This tool only collects raw model answers and writes a structured Markdown file.
It does not evaluate answers, call any model, or generate JSON/HTML reports.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import socket
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTOR_ANSWERS_DIR = REPO_ROOT / "responses" / "i-am-not-an-actor"
FEICHENG_ANSWERS_DIR = REPO_ROOT / "responses" / "seal-of-the-ruined-city"
STEAM_ANSWERS_DIR = REPO_ROOT / "responses" / "era-of-wild-tide-steam-72h"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 30 * 1024 * 1024

SUITES: dict[str, dict[str, Any]] = {
    "actor": {
        "label": "《我不是演员》",
        "test_name": "《我不是演员》",
        "prompt_variant": "C+ 强化版",
        "answers_dir": ACTOR_ANSWERS_DIR,
        "rounds": ["第一轮回答", "第二轮回答", "第三轮回答"],
    },
    "feicheng": {
        "label": "《废城授印》",
        "test_name": "《废城授印》",
        "prompt_variant": "五轮完整",
        "answers_dir": FEICHENG_ANSWERS_DIR,
        "rounds": ["第一轮回答", "第二轮回答", "第三轮回答", "第四轮回答", "第五轮回答"],
    },
    "steam": {
        "label": "《荒潮纪元：Steam首发72小时》",
        "test_name": "《荒潮纪元：Steam首发72小时》",
        "prompt_variant": "三段战情完整",
        "answers_dir": STEAM_ANSWERS_DIR,
        "rounds": ["第一轮回答", "第二轮回答", "第三轮回答"],
    },
}


def safe_model_name(name: str) -> str:
    """Return a filesystem-safe model name while preserving readable text."""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or "未命名模型"


def get_suite(suite_key: str) -> dict[str, Any]:
    suite = SUITES.get(suite_key)
    if suite is None:
        raise ValueError("未知题组：" + suite_key)
    return suite


def unique_output_path(model_name: str, answers_dir: Path) -> Path:
    safe_name = safe_model_name(model_name)
    base = answers_dir / f"{safe_name}模型答案.md"
    if not base.exists():
        return base
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return answers_dir / f"{safe_name}模型答案-{stamp}.md"


def build_markdown(
    suite_key: str,
    model_name: str,
    prompt_variant: str,
    rounds: list[str],
    today: str | None = None,
) -> str:
    suite = get_suite(suite_key)
    round_labels = list(suite["rounds"])
    today = today or datetime.now().strftime("%Y-%m-%d")
    variant = prompt_variant.strip() or str(suite["prompt_variant"])
    lines = [
        f"# {model_name}模型答案",
        "",
        f"- 模型：{model_name}",
        f"- 日期：{today}",
        f"- 题组：{suite['label']}",
        f"- 题目：{suite['test_name']}",
        f"- prompt_variant：{variant}",
        "- 类型：raw-response",
        f"- 轮次：{len(round_labels)}轮完整",
        "- 状态：ready-for-review",
        "",
    ]
    for label, answer in zip(round_labels, rounds, strict=True):
        lines.extend(
            [
                f"## {model_name}{label}：",
                "",
                answer.rstrip(),
                "",
            ]
        )
    return "\n".join(lines)


def validate_payload(data: dict[str, Any]) -> tuple[str, str, str, list[str]]:
    suite_key = str(data.get("suite") or "actor").strip() or "actor"
    suite = get_suite(suite_key)
    round_labels = list(suite["rounds"])
    model_name = str(data.get("model_name") or "").strip()
    prompt_variant = str(data.get("prompt_variant") or "").strip() or str(suite["prompt_variant"])

    raw_rounds = data.get("rounds")
    if isinstance(raw_rounds, list):
        rounds = [str(item or "").strip() for item in raw_rounds]
    else:
        # Backward compatibility with the original 《我不是演员》 collector API.
        rounds = [
            str(data.get("first_round") or "").strip(),
            str(data.get("second_round") or "").strip(),
            str(data.get("third_round") or "").strip(),
        ]

    missing: list[str] = []
    if not model_name:
        missing.append("模型名")
    if len(rounds) != len(round_labels):
        raise ValueError(f"{suite['label']} 需要 {len(round_labels)} 轮回答")
    for label, answer in zip(round_labels, rounds, strict=True):
        if not answer:
            missing.append(label)
    if missing:
        raise ValueError("缺少：" + "、".join(missing))

    return suite_key, model_name, prompt_variant, rounds


def save_answer_file(data: dict[str, Any]) -> Path:
    suite_key, model_name, prompt_variant, rounds = validate_payload(data)
    answers_dir = Path(get_suite(suite_key)["answers_dir"])
    answers_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(model_name, answers_dir)
    markdown = build_markdown(suite_key, model_name, prompt_variant, rounds)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>模型测试回答采集器</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f3ee;
      --surface: #fffdfa;
      --ink: #1d1d1b;
      --muted: #68645d;
      --line: #d8d2c6;
      --accent: #b3261e;
      --accent-dark: #861b16;
      --ok: #176f45;
      --warn: #9a5a00;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
      line-height: 1.5;
    }
    main {
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }
    header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 28px;
      letter-spacing: 0;
    }
    .sub {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }
    .steps {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin: 16px 0;
    }
    .step {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.55);
      border-radius: 6px;
      padding: 10px 12px;
      color: var(--muted);
      font-size: 13px;
      min-height: 44px;
    }
    .step.active {
      border-color: var(--accent);
      color: var(--ink);
      background: #fff;
      font-weight: 650;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 12px 34px rgba(28, 24, 16, .06);
    }
    .row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
    }
    label {
      display: block;
      font-weight: 650;
      margin-bottom: 7px;
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 11px 12px;
      font: inherit;
      letter-spacing: 0;
    }
    input:focus, select:focus, textarea:focus {
      outline: 2px solid rgba(179, 38, 30, .16);
      border-color: var(--accent);
    }
    textarea {
      min-height: min(56vh, 520px);
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 14px;
      line-height: 1.55;
      white-space: pre-wrap;
    }
    .actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 16px;
    }
    .button-group {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      padding: 10px 14px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    button.primary:hover { background: var(--accent-dark); }
    button:disabled {
      cursor: not-allowed;
      opacity: .55;
    }
    .status {
      min-height: 22px;
      color: var(--muted);
      font-size: 14px;
      overflow-wrap: anywhere;
    }
    .status.ok { color: var(--ok); }
    .status.err { color: var(--accent); }
    .status.warn { color: var(--warn); }
    .hidden { display: none; }
    .review {
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
      color: var(--muted);
      font-size: 14px;
    }
    .review code {
      color: var(--ink);
      background: #f0ede6;
      border-radius: 4px;
      padding: 2px 5px;
      overflow-wrap: anywhere;
    }
    @media (max-width: 760px) {
      header, .actions { align-items: stretch; flex-direction: column; }
      .steps, .row { grid-template-columns: 1fr; }
      main { width: min(100vw - 20px, 1120px); padding-top: 16px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>模型测试回答采集器</h1>
        <p class="sub">只保存 raw md，不评审，不生成 JSON，不调用模型。</p>
      </div>
      <div class="status" id="topStatus"></div>
    </header>

    <div class="steps" aria-label="采集步骤">
      <div class="step active" data-step-label="0">1. 模型信息</div>
      <div class="step" data-step-label="1">2. 第一轮回答</div>
      <div class="step" data-step-label="2">3. 第二轮回答</div>
      <div class="step" data-step-label="3">4. 第三轮回答</div>
      <div class="step hidden" data-step-label="4">5. 第四轮回答</div>
      <div class="step hidden" data-step-label="5">6. 第五轮保存</div>
    </div>

    <section class="panel" id="metaPanel">
      <div class="row">
        <div>
          <label for="modelName">模型名</label>
          <input id="modelName" list="modelOptions" autocomplete="off" placeholder="选择常用模型，或直接手打">
          <datalist id="modelOptions">
            <option value="Gemini"></option>
            <option value="ChatGPT"></option>
            <option value="DeepSeek V4 Pro"></option>
            <option value="Kimi K2.6"></option>
            <option value="GLM5.1"></option>
            <option value="MiniMax M2.7"></option>
            <option value="MimoV2.5Pro"></option>
            <option value="豆包"></option>
            <option value="Claude Opus 4.6"></option>
          </datalist>
        </div>
        <div>
          <label for="suiteSelect">题组</label>
          <select id="suiteSelect">
            <option value="actor" selected>《我不是演员》 / 三轮</option>
            <option value="feicheng">《废城授印》 / 五轮</option>
            <option value="steam">《荒潮纪元：Steam首发72小时》 / 三轮</option>
          </select>
        </div>
      </div>
      <div class="actions">
        <div class="status" id="metaHint">三轮必须全部录入后才会写文件。</div>
        <div class="button-group">
          <button class="primary" id="startBtn" type="button">开始录入第一轮</button>
        </div>
      </div>
    </section>

    <section class="panel hidden" id="roundPanel">
      <label id="roundLabel" for="roundText">第一轮回答</label>
      <textarea id="roundText" spellcheck="false" placeholder="粘贴当前轮模型原始回答"></textarea>
      <div class="actions">
        <div class="status" id="roundStatus"></div>
        <div class="button-group">
          <button id="backBtn" type="button">返回上一轮</button>
          <button class="primary" id="nextBtn" type="button">确认本轮</button>
        </div>
      </div>
      <div class="review" id="reviewBox"></div>
    </section>
  </main>

  <script>
    const state = {
      step: 0,
      rounds: [],
      savedPath: ""
    };

    const suiteConfig = {
      actor: {
        label: "《我不是演员》",
        promptVariant: "C+ 强化版",
        labels: ["第一轮回答", "第二轮回答", "第三轮回答"]
      },
      feicheng: {
        label: "《废城授印》",
        promptVariant: "五轮完整",
        labels: ["第一轮回答", "第二轮回答", "第三轮回答", "第四轮回答", "第五轮回答"]
      },
      steam: {
        label: "《荒潮纪元：Steam首发72小时》",
        promptVariant: "三段战情完整",
        labels: ["第一轮回答", "第二轮回答", "第三轮回答"]
      }
    };

    const metaPanel = document.getElementById("metaPanel");
    const roundPanel = document.getElementById("roundPanel");
    const modelName = document.getElementById("modelName");
    const suiteSelect = document.getElementById("suiteSelect");
    const roundText = document.getElementById("roundText");
    const roundLabel = document.getElementById("roundLabel");
    const roundStatus = document.getElementById("roundStatus");
    const topStatus = document.getElementById("topStatus");
    const metaHint = document.getElementById("metaHint");
    const reviewBox = document.getElementById("reviewBox");
    const startBtn = document.getElementById("startBtn");
    const nextBtn = document.getElementById("nextBtn");
    const backBtn = document.getElementById("backBtn");

    function currentConfig() {
      return suiteConfig[suiteSelect.value] || suiteConfig.actor;
    }

    function resetRounds() {
      state.rounds = currentConfig().labels.map(() => "");
      state.savedPath = "";
      state.step = 0;
    }

    function setStatus(el, text, kind = "") {
      el.textContent = text;
      el.className = "status" + (kind ? " " + kind : "");
    }

    function updateSteps() {
      const labels = currentConfig().labels;
      document.querySelectorAll("[data-step-label]").forEach((node) => {
        const step = Number(node.dataset.stepLabel);
        node.classList.toggle("hidden", step > labels.length);
        node.classList.toggle("active", step === state.step);
        if (step > 0 && step <= labels.length) {
          node.textContent = `${step + 1}. ${step === labels.length ? labels[step - 1].replace("回答", "保存") : labels[step - 1]}`;
        }
      });
      metaHint.textContent = `${labels.length}轮必须全部录入后才会写文件。`;
    }

    function showRound(step) {
      const labels = currentConfig().labels;
      state.step = step;
      metaPanel.classList.add("hidden");
      roundPanel.classList.remove("hidden");
      roundLabel.textContent = labels[step - 1];
      roundText.value = state.rounds[step - 1] || "";
      nextBtn.textContent = step === labels.length ? `确认${labels[step - 1].replace("回答", "")}并保存 md` : "确认本轮";
      backBtn.disabled = step === 1;
      setStatus(roundStatus, "");
      updateReview();
      updateSteps();
      roundText.focus();
    }

    function updateReview() {
      const labels = currentConfig().labels;
      const safeName = modelName.value.trim() || "未命名模型";
      const filled = state.rounds.map((text, idx) => `${labels[idx]}：${text.trim() ? "已确认" : "待录入"}`);
      reviewBox.innerHTML = `当前题组：<code>${escapeHtml(currentConfig().label)}</code><br>当前模型：<code>${escapeHtml(safeName)}</code><br>${filled.map(escapeHtml).join("<br>")}`;
    }

    function escapeHtml(text) {
      return String(text).replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[ch]));
    }

    async function saveAll() {
      nextBtn.disabled = true;
      setStatus(roundStatus, "正在保存...", "");
      try {
        const response = await fetch("/api/save", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            suite: suiteSelect.value,
            model_name: modelName.value,
            prompt_variant: currentConfig().promptVariant,
            rounds: state.rounds
          })
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "保存失败");
        }
        state.savedPath = data.path;
        setStatus(roundStatus, `已保存：${data.path}`, "ok");
        setStatus(topStatus, "raw md 已生成", "ok");
        nextBtn.disabled = true;
        backBtn.disabled = false;
      } catch (err) {
        setStatus(roundStatus, err.message || String(err), "err");
        nextBtn.disabled = false;
      }
    }

    startBtn.addEventListener("click", () => {
      if (!modelName.value.trim()) {
        setStatus(topStatus, "请先输入模型名。", "err");
        modelName.focus();
        return;
      }
      setStatus(topStatus, "");
      if (state.rounds.length !== currentConfig().labels.length) {
        resetRounds();
      }
      showRound(1);
    });

    nextBtn.addEventListener("click", async () => {
      const labels = currentConfig().labels;
      const text = roundText.value.trim();
      if (!text) {
        setStatus(roundStatus, `请粘贴${labels[state.step - 1]}。`, "err");
        roundText.focus();
        return;
      }
      state.rounds[state.step - 1] = roundText.value;
      if (state.step < labels.length) {
        showRound(state.step + 1);
      } else {
        await saveAll();
      }
    });

    backBtn.addEventListener("click", () => {
      if (state.step <= 1) return;
      state.rounds[state.step - 1] = roundText.value;
      showRound(state.step - 1);
    });

    suiteSelect.addEventListener("change", () => {
      resetRounds();
      setStatus(topStatus, "");
      updateSteps();
      updateReview();
    });

    resetRounds();
    updateSteps();
  </script>
</body>
</html>
"""


class CollectorHandler(BaseHTTPRequestHandler):
    server_version = "BenchmarkAnswerCollector/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}", file=sys.stderr)

    def send_text(self, status: int, content: str, content_type: str = "text/plain; charset=utf-8") -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        self.send_text(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("", "/"):
            self.send_text(200, HTML_PAGE, "text/html; charset=utf-8")
            return
        if parsed.path == "/health":
            self.send_json(200, {"ok": True})
            return
        self.send_text(404, "Not found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/save":
            self.send_text(404, "Not found")
            return

        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError:
            self.send_json(400, {"error": "Content-Length 无效"})
            return
        if length <= 0:
            self.send_json(400, {"error": "请求体为空"})
            return
        if length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "请求体过大"})
            return

        try:
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("请求体必须是 JSON 对象")
            output_path = save_answer_file(data)
        except json.JSONDecodeError as exc:
            self.send_json(400, {"error": f"JSON 解析失败：{exc}"})
            return
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return
        except OSError as exc:
            self.send_json(500, {"error": f"写入失败：{exc}"})
            return

        self.send_json(200, {"ok": True, "path": str(output_path)})


def find_available_port(host: str, preferred_port: int) -> int:
    if preferred_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex((host, preferred_port)) != 0:
            return preferred_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def run_server(host: str, port: int) -> None:
    chosen_port = find_available_port(host, port)
    server = ThreadingHTTPServer((host, chosen_port), CollectorHandler)
    url = f"http://{host}:{chosen_port}/"
    print(f"Benchmark answer collector: {url}", flush=True)
    print(f"《我不是演员》 output directory: {ACTOR_ANSWERS_DIR}", flush=True)
    print(f"《废城授印》 output directory: {FEICHENG_ANSWERS_DIR}", flush=True)
    print(f"《荒潮纪元》 output directory: {STEAM_ANSWERS_DIR}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping benchmark answer collector.", flush=True)
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="《我不是演员》 / 《废城授印》 / 《荒潮纪元》模型回答本地网页采集器")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 8765；若占用则自动换空闲端口")
    args = parser.parse_args()
    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
