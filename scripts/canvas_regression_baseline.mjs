#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const DEFAULT_BASE_URL = "http://localhost:3000";
const DEFAULT_OUT_DIR = "docs/design-references/regression";
const DEFAULT_VIEWPORT = { width: 1440, height: 900 };
const DEFAULT_TIMEOUT_MS = 30_000;

const args = parseArgs(process.argv.slice(2));
const baseUrl = String(args["base-url"] ?? process.env.ZEUS_BASE_URL ?? DEFAULT_BASE_URL).replace(/\/$/, "");
const outDir = path.resolve(String(args.out ?? DEFAULT_OUT_DIR));
const viewport = parseViewport(String(args.viewport ?? `${DEFAULT_VIEWPORT.width}x${DEFAULT_VIEWPORT.height}`));
const strict = Boolean(args.strict);
const skipScreenshots = Boolean(args["skip-screenshots"]);

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});

async function main() {
  if (!globalThis.WebSocket) {
    throw new Error("Node.js WebSocket support is required. Use Node 22+.");
  }

  await assertReachable(baseUrl);
  await mkdir(outDir, { recursive: true });

  const chromePath = String(args["chrome-path"] ?? process.env.CHROME_PATH ?? findChromePath() ?? "");
  if (!chromePath) {
    throw new Error("Chrome was not found. Set CHROME_PATH to a Chromium/Chrome executable.");
  }

  const port = await findFreePort();
  const userDataDir = await mkdtemp(path.join(os.tmpdir(), "zeus-canvas-cdp-"));
  const chrome = launchChrome(chromePath, port, userDataDir, viewport);

  try {
    await waitForChrome(port);
    const target = await createTarget(port);
    const cdp = await CdpSession.connect(target.webSocketDebuggerUrl);
    await preparePage(cdp, viewport);

    const scenarios = [];
    scenarios.push(
      await captureScenario(cdp, {
        name: "world-map-light-desktop",
        url: `${baseUrl}/world-map`,
        waitFor: ["[data-testid='world-map-region-index']", "[data-testid='world-map-zoom-controls']"],
      })
    );
    scenarios.push(
      await captureScenario(cdp, {
        name: "world-map-enhanced-desktop",
        url: `${baseUrl}/world-map`,
        waitFor: ["[data-testid='world-map-region-index']"],
        actions: [
          { click: "[data-testid='world-map-renderer-toggle-webgl-ready']" },
          { waitFor: "[data-testid='world-map-webgl-preview']" },
        ],
      })
    );
    scenarios.push(
      await captureScenario(cdp, {
        name: "world-map-filter-open",
        url: `${baseUrl}/world-map`,
        waitFor: ["[data-testid='world-map-filter-toggle']"],
        actions: [
          { click: "[data-testid='world-map-filter-toggle']" },
          { waitFor: "[data-testid='world-map-filter-popover']" },
        ],
      })
    );
    scenarios.push(
      await captureScenario(cdp, {
        name: "world-map-region-modal",
        url: `${baseUrl}/world-map`,
        waitFor: ["[data-testid='world-map-region-index']"],
        actions: [
          { click: "[data-testid^='world-map-region-index-item-']" },
          { waitFor: "[data-testid='world-map-region-dossier']" },
        ],
      })
    );
    scenarios.push(
      await captureScenario(cdp, {
        name: "causal-web-desktop",
        url: `${baseUrl}/causal-web`,
        waitFor: [".causal-web-flow"],
      })
    );

    const report = {
      baseUrl,
      generatedAt: new Date().toISOString(),
      strict,
      thresholds: {
        maxDomNodes: 6500,
        maxJsHeapMb: 180,
        minFps: 24,
      },
      viewport,
      scenarios,
    };
    report.summary = summarizeReport(report);

    const reportPath = path.join(outDir, "canvas-performance-baseline.json");
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);

    const failed = report.summary.failedScenarios.length;
    console.log(`Canvas baseline written to ${path.relative(process.cwd(), reportPath)}`);
    for (const scenario of scenarios) {
      console.log(
        [
          scenario.ok ? "ok" : "warn",
          scenario.name,
          `fps=${scenario.stats.fps}`,
          `dom=${scenario.stats.domNodes}`,
          `heap=${scenario.stats.jsHeapMb}MB`,
          scenario.screenshot ? `screenshot=${path.relative(process.cwd(), scenario.screenshot)}` : null,
        ]
          .filter(Boolean)
          .join(" ")
      );
    }

    if (strict && failed > 0) {
      throw new Error(`Canvas baseline failed for ${failed} scenario(s): ${report.summary.failedScenarios.join(", ")}`);
    }

    await cdp.close();
  } finally {
    chrome.kill("SIGTERM");
    await rm(userDataDir, { force: true, recursive: true });
  }
}

async function captureScenario(cdp, scenario) {
  await navigate(cdp, scenario.url);
  for (const selector of scenario.waitFor ?? []) {
    await waitForSelector(cdp, selector);
  }
  for (const action of scenario.actions ?? []) {
    if (action.click) {
      await clickSelector(cdp, action.click);
      await settle(cdp, 350);
    }
    if (action.waitFor) {
      await waitForSelector(cdp, action.waitFor);
    }
  }
  await settle(cdp, 1_500);

  const stats = await collectStats(cdp);
  const screenshot = skipScreenshots ? null : await captureScreenshot(cdp, scenario.name);
  const ok = stats.fps >= 24 && stats.domNodes <= 6500 && stats.jsHeapMb <= 180;
  return {
    checks: {
      domNodesWithinBudget: stats.domNodes <= 6500,
      fpsWithinBudget: stats.fps >= 24,
      jsHeapWithinBudget: stats.jsHeapMb <= 180,
    },
    name: scenario.name,
    ok,
    screenshot,
    stats,
    url: scenario.url,
  };
}

async function preparePage(cdp, size) {
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Performance.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    deviceScaleFactor: 1,
    height: size.height,
    mobile: false,
    width: size.width,
  });
}

async function navigate(cdp, url) {
  const loadEvent = cdp.waitForEvent("Page.loadEventFired", DEFAULT_TIMEOUT_MS);
  await cdp.send("Page.navigate", { url });
  await loadEvent;
  await settle(cdp, 500);
}

async function collectStats(cdp) {
  const metricsResponse = await cdp.send("Performance.getMetrics");
  const metrics = Object.fromEntries(metricsResponse.metrics.map((metric) => [metric.name, metric.value]));
  const pageStats = await evaluate(cdp, `(${pageStatsExpression})()`, { timeoutMs: 12_000 });
  const jsHeapMb = roundMb(metrics.JSHeapUsedSize ?? 0);

  return {
    canvases: pageStats.canvases,
    causalNodes: pageStats.causalNodes,
    domNodes: pageStats.domNodes,
    fps: pageStats.fps,
    jsHeapMb,
    layoutCount: Math.round(metrics.LayoutCount ?? 0),
    mapLabels: pageStats.mapLabels,
    mapLibreReady: pageStats.mapLibreReady,
    recalcStyleCount: Math.round(metrics.RecalcStyleCount ?? 0),
    svgNodes: pageStats.svgNodes,
    taskDurationMs: Math.round((metrics.TaskDuration ?? 0) * 1000),
    webglCanvases: pageStats.webglCanvases,
  };
}

async function captureScreenshot(cdp, name) {
  const response = await cdp.send("Page.captureScreenshot", {
    captureBeyondViewport: false,
    format: "png",
    fromSurface: true,
  });
  const filePath = path.join(outDir, `${name}.png`);
  await writeFile(filePath, Buffer.from(response.data, "base64"));
  return filePath;
}

async function waitForSelector(cdp, selector, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const exists = await evaluate(
      cdp,
      `Boolean(document.querySelector(${JSON.stringify(selector)}))`,
      { timeoutMs: 2_000 }
    );
    if (exists) return;
    await sleep(250);
  }
  throw new Error(`Timed out waiting for selector: ${selector}`);
}

async function clickSelector(cdp, selector) {
  const clicked = await evaluate(
    cdp,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return false;
      element.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, clientX: 10, clientY: 10 }));
      element.click();
      return true;
    })()`
  );
  if (!clicked) throw new Error(`Could not click selector: ${selector}`);
}

async function settle(cdp, ms) {
  await evaluate(
    cdp,
    `new Promise((resolve) => window.setTimeout(resolve, ${Number(ms)}))`,
    { timeoutMs: ms + 2_000 }
  );
}

async function evaluate(cdp, expression, options = {}) {
  const response = await cdp.send(
    "Runtime.evaluate",
    {
      awaitPromise: true,
      expression,
      returnByValue: true,
      userGesture: true,
    },
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  );
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text ?? "Runtime.evaluate failed");
  }
  return response.result.value;
}

const pageStatsExpression = async function pageStatsExpression() {
  const fps = await new Promise((resolve) => {
    let frames = 0;
    let startedAt = 0;
    function tick(timestamp) {
      if (!startedAt) startedAt = timestamp;
      frames += 1;
      if (timestamp - startedAt < 1000) {
        window.requestAnimationFrame(tick);
      } else {
        resolve(Math.round((frames * 1000) / Math.max(timestamp - startedAt, 1)));
      }
    }
    window.requestAnimationFrame(tick);
  });

  return {
    canvases: document.querySelectorAll("canvas").length,
    causalNodes: document.querySelectorAll(".react-flow__node").length,
    domNodes: document.querySelectorAll("*").length,
    fps,
    mapLabels: document.querySelectorAll("[data-testid='world-map-region-label']").length,
    mapLibreReady: Boolean(document.querySelector("[data-testid='world-map-maplibre-status-ready']")),
    svgNodes: document.querySelectorAll("svg").length,
    webglCanvases: document.querySelectorAll("[data-testid='world-map-webgl-preview'] canvas").length,
  };
};

function summarizeReport(report) {
  const failedScenarios = report.scenarios.filter((scenario) => !scenario.ok).map((scenario) => scenario.name);
  return {
    failedScenarios,
    ok: failedScenarios.length === 0,
    scenarioCount: report.scenarios.length,
  };
}

function parseArgs(values) {
  const parsed = {};
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (!value.startsWith("--")) continue;
    const key = value.slice(2);
    const next = values[index + 1];
    if (!next || next.startsWith("--")) {
      parsed[key] = true;
      continue;
    }
    parsed[key] = next;
    index += 1;
  }
  return parsed;
}

function parseViewport(value) {
  const match = value.match(/^(\d+)x(\d+)$/i);
  if (!match) return DEFAULT_VIEWPORT;
  return { width: Number(match[1]), height: Number(match[2]) };
}

function findChromePath() {
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function launchChrome(chromePath, port, userDataDir, size) {
  return spawn(
    chromePath,
    [
      "--headless=new",
      "--disable-background-networking",
      "--disable-default-apps",
      "--disable-dev-shm-usage",
      "--disable-features=Translate,BackForwardCache",
      "--disable-popup-blocking",
      "--hide-scrollbars",
      "--no-default-browser-check",
      "--no-first-run",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      `--window-size=${size.width},${size.height}`,
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] }
  );
}

async function createTarget(port) {
  return devtoolsJson(port, "/json/new?about:blank", "PUT");
}

async function waitForChrome(port) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < DEFAULT_TIMEOUT_MS) {
    try {
      await devtoolsJson(port, "/json/version");
      return;
    } catch {
      await sleep(200);
    }
  }
  throw new Error("Timed out waiting for Chrome DevTools endpoint.");
}

async function devtoolsJson(port, requestPath, method = "GET") {
  const body = await httpRequest({ hostname: "127.0.0.1", method, path: requestPath, port });
  return JSON.parse(body);
}

async function assertReachable(url) {
  try {
    await httpRequest(new URL(url));
  } catch (error) {
    throw new Error(`Base URL is not reachable: ${url}. Start Zeus first with scripts/local_smoke.sh --start.`);
  }
}

function httpRequest(options) {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        if ((res.statusCode ?? 500) >= 400) {
          reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 160)}`));
          return;
        }
        resolve(body);
      });
    });
    req.on("error", reject);
    req.setTimeout(DEFAULT_TIMEOUT_MS, () => {
      req.destroy(new Error("HTTP request timed out"));
    });
    req.end();
  });
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close(() => {
        if (!port) {
          reject(new Error("Could not allocate a free port"));
          return;
        }
        resolve(port);
      });
    });
  });
}

function roundMb(bytes) {
  return Math.round((bytes / 1024 / 1024) * 10) / 10;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

class CdpSession {
  constructor(socket) {
    this.nextId = 1;
    this.pending = new Map();
    this.eventWaiters = new Map();
    this.socket = socket;

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id && this.pending.has(message.id)) {
        const { reject, resolve, timeout } = this.pending.get(message.id);
        clearTimeout(timeout);
        this.pending.delete(message.id);
        if (message.error) {
          reject(new Error(`${message.error.message}: ${message.error.data ?? ""}`));
        } else {
          resolve(message.result ?? {});
        }
        return;
      }

      if (message.method && this.eventWaiters.has(message.method)) {
        const waiters = this.eventWaiters.get(message.method) ?? [];
        this.eventWaiters.delete(message.method);
        for (const waiter of waiters) {
          clearTimeout(waiter.timeout);
          waiter.resolve(message.params ?? {});
        }
      }
    });
  }

  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });
    return new CdpSession(socket);
  }

  send(method, params = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Timed out running CDP command ${method}`));
      }, timeoutMs);
      this.pending.set(id, { reject, resolve, timeout });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  waitForEvent(method, timeoutMs = DEFAULT_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        const waiters = (this.eventWaiters.get(method) ?? []).filter((waiter) => waiter.timeout !== timeout);
        if (waiters.length > 0) this.eventWaiters.set(method, waiters);
        else this.eventWaiters.delete(method);
        reject(new Error(`Timed out waiting for CDP event ${method}`));
      }, timeoutMs);
      const waiters = this.eventWaiters.get(method) ?? [];
      waiters.push({ resolve, timeout });
      this.eventWaiters.set(method, waiters);
    });
  }

  close() {
    this.socket.close();
  }
}
