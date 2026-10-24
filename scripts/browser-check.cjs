"use strict";

// Real browser + ASR + process-restart checks, using ignored synthetic test data.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const artifacts = path.join(root, "validation-artifacts");
const dataDir = fs.mkdtempSync(path.join(artifacts, "browser-data-"));
const base = "http://127.0.0.1:8876";
const python = process.env.LISTENFLOW_TEST_PYTHON || path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let server, browser;
const errors = [], network = [];

async function startServer() {
  try {
    await fetch(base + "/");
    throw new Error("Port 8876 is already in use; stop that service before running this check.");
  } catch (error) {
    if (error.message.startsWith("Port 8876")) throw error;
  }
  server = spawn(python, ["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8876"], {
    cwd: root, windowsHide: true,
    env: { ...process.env, LISTENFLOW_DATA_DIR: dataDir, LIBRARY_DB: path.join(dataDir, "library.db"), HF_HUB_OFFLINE: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const log = fs.createWriteStream(path.join(dataDir, "server.log"), { flags: "a" });
  server.stdout.pipe(log); server.stderr.pipe(log);
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error("Server exited; see " + dataDir);
    try { if ((await fetch(base + "/")).ok) return; } catch (_) {}
    await delay(100);
  }
  throw new Error("Server startup timed out.");
}
async function stopServer() {
  if (!server) return;
  if (process.platform === "win32") spawnSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { windowsHide: true });
  else server.kill("SIGTERM");
  server = null;
  for (let i = 0; i < 50; i++) {
    try { await fetch(base + "/"); } catch (_) { return; }
    await delay(100);
  }
  throw new Error("Server did not stop; cannot claim restart persistence.");
}
async function main() {
  assert.ok(fs.existsSync(path.join(artifacts, "clear-speech.wav")), "Run scripts/validate_local.py first.");
  await startServer();
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    const url = r.url();
    if (!url.startsWith(base) && !url.startsWith("blob:" + base) && !url.startsWith("data:")) network.push(url);
  });
  await page.goto(base);
  await page.locator("#model").selectOption("tiny");
  await page.locator("#file").setInputFiles(path.join(artifacts, "clear-speech.wav"));
  const posted = page.waitForResponse((r) => r.url() === base + "/api/jobs" && r.request().method() === "POST");
  await page.locator("#go").click();
  const id = (await (await posted).json()).job_id;
  await page.waitForFunction(() => document.querySelector("#rtitle").textContent.startsWith("Transcript:"), null, { timeout: 120000 });
  const item = await (await fetch(base + "/api/library/" + id)).json();
  assert.equal(item.status, "done");
  assert.ok(await page.locator(".seg-text .w").count(), "Speech must produce word spans.");
  assert.ok(await page.evaluate(() => practiceRanges(jobs.get(activeId)).length > jobs.get(activeId).segments.length), "Sentence replay must split multi-sentence ASR segments.");
  await page.locator(".seg-text").first().click();
  await page.waitForFunction(() => document.querySelector(".wnow"));
  await page.locator("#playbackSpeed").selectOption("0.75");
  assert.equal(await page.locator("#player").evaluate((el) => el.playbackRate), .75);
  await page.locator("#player").evaluate((el) => el.pause());
  await page.locator("#smartReplay").click();
  assert.ok(await page.locator("#player").evaluate((el) => !el.paused));
  await page.locator("#loopToggle").click();
  assert.equal(await page.locator("#loopToggle").getAttribute("aria-pressed"), "true");
  const seg = item.segments[0];
  await page.locator("#player").evaluate((el, range) => { el.currentTime = range.end; el.dispatchEvent(new Event("timeupdate")); }, seg);
  assert.ok((await page.locator("#player").evaluate((el) => el.currentTime)) < seg.end);
  await page.locator("#loopToggle").click();
  await page.locator("#player").evaluate((el) => el.pause());

  await page.locator("#editToggle").click();
  await page.locator(".seg-text").first().fill("Did you get it?");
  await page.locator("#editToggle").click();
  await page.waitForFunction(() => document.querySelector("#editToggle").textContent === "Edit");
  assert.equal(await page.locator(".seg-text").first().textContent(), "Did you get it?");
  await page.locator(".seg-actions button").filter({ hasText: "Save clip" }).first().click();
  await page.locator("#savedClips .practice-clip").waitFor();
  await page.locator(".seg-actions button").filter({ hasText: "Patterns" }).first().click();
  await page.locator("#patternList .pattern-card").first().waitFor();
  assert.match(await page.locator("#patternList").textContent(), /Possible pattern/);
  assert.match(await page.locator("#patternPanel .study-note").first().textContent(), /not been confirmed/);
  for (const fmt of ["txt", "srt"]) {
    const downloadPromise = page.waitForEvent("download");
    await page.locator("#dl-" + fmt).click();
    const download = await downloadPromise;
    const file = path.join(dataDir, "edited." + fmt);
    await download.saveAs(file);
    assert.match(fs.readFileSync(file, "utf8"), /Did you get it\?/);
  }
  assert.equal(await page.evaluate(() => ts(59.9996)), "00:01:00,000");
  assert.equal(await page.evaluate(() => ts(3599.9996)), "01:00:00,000");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(artifacts, "desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(artifacts, "mobile.png"), fullPage: true });
  const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")].filter((el) => {
    const box = el.getBoundingClientRect(); return box.width && box.right > innerWidth + 1;
  }).slice(0, 12).map((el) => ({ tag: el.tagName, id: el.id, cls: el.className, width: el.getBoundingClientRect().width })));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "Mobile layout overflows horizontally: " + JSON.stringify(overflow));
  await page.setViewportSize({ width: 1440, height: 1100 });

  await stopServer();
  await startServer();
  await page.goto(base + "/?recording=" + encodeURIComponent(id));
  await page.waitForFunction(() => document.querySelector("#rtitle").textContent.startsWith("Transcript:"));
  await page.waitForFunction(() => document.querySelector("#player")?.readyState >= 1);
  assert.equal(await page.locator(".seg-text").first().textContent(), "Did you get it?");
  await page.locator("#savedClips .practice-clip").waitFor();
  await page.locator("#savedClips button").filter({ hasText: "Replay clip" }).click();
  assert.ok(await page.locator("#player").evaluate((el) => !el.paused));
  await page.locator("#libraryBtn").click();
  await page.locator(".lib-del").click();
  await page.waitForFunction(() => document.querySelectorAll(".lib-card").length === 0);
  assert.equal((await fetch(base + "/api/library/" + id + "/media")).status, 404);
  assert.ok(!fs.existsSync(path.join(dataDir, "uploads", id)));

  await page.locator("#libClose").click();
  await page.locator("#file").setInputFiles({ name: "corrupt.wav", mimeType: "audio/wav", buffer: Buffer.from("not audio") });
  await page.locator("#go").click();
  await page.locator("#retryJob").waitFor();
  const retryResponse = page.waitForResponse((r) => r.url().endsWith("/retry"));
  await page.locator("#retryJob").click();
  assert.equal((await retryResponse).status(), 200);
  await page.locator("#retryJob").waitFor();
  assert.match(await page.locator("#status").textContent(), /Could not read audio/);
  assert.deepEqual(errors, [], "Browser JavaScript errors");
  assert.deepEqual(network, [], "Unexpected external browser requests");
  fs.writeFileSync(path.join(dataDir, "result.json"), JSON.stringify({ passed: true, recordingId: id, browserErrors: errors, externalRequests: network }, null, 2));
  console.log("PASS: upload, real ASR, highlighting, seek, speed, replay, loop, edits, clips, candidates, exports, actual process restart, playback, deletion, retry, desktop/mobile layout.");
  console.log("Evidence: " + dataDir);
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  await stopServer();
});
