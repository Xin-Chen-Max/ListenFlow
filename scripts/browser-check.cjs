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
const errors = [], network = [], patternRequests = [];

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
    if (url.includes("/patterns?")) patternRequests.push(url);
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
  assert.ok(await page.locator(".sentence-text .w").count(), "Speech must produce word spans.");
  assert.ok(await page.evaluate(() => practiceRanges(jobs.get(activeId)).length > jobs.get(activeId).segments.length), "Sentence replay must split multi-sentence ASR segments.");
  await page.locator(".sentence-text").first().click();
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
  await page.locator('.seg .pattern-cue[data-rule-id="assimilation.yod"]').first().waitFor();
  assert.equal(await page.locator("#patternPanel").count(), 0, "Details belong underneath the sentence.");
  await page.locator('.seg .pattern-cue[data-rule-id="assimilation.yod"]').first().click();
  const details = page.locator(".sentence-details[open] .pattern-detail-list").first();
  await details.locator(".pattern-card").first().waitFor();
  assert.match(await details.textContent(), /Possible pattern/);
  assert.match(await details.textContent(), /Not confirmed in the recording/);
  assert.match(await details.textContent(), /Conditional opportunity/);
  await details.locator(".pattern-card summary").first().click();
  assert.match(await details.textContent(), /Uncalibrated/);
  assert.match(await details.textContent(), /not measured audio/);
  await details.locator(".pattern-card button").first().click();
  assert.ok(await page.locator("#player").evaluate((el) => !el.paused));
  await page.locator("#player").evaluate((el) => el.pause());

  const patternRoute = base + "/api/library/" + id + "/patterns?*";
  const refreshDetails = () => page.evaluate(() => {
    const job = jobs.get(activeId); return renderSentenceDetails(job, job.segments[0], 0, job.segments[0].sentenceUnits[0], true);
  });
  await page.route(patternRoute, (route) => new URL(route.request().url()).searchParams.get("view") === "full"
    ? route.fulfill({ status: 503, body: "unavailable" }) : route.continue());
  await refreshDetails();
  await details.locator(".pattern-error").waitFor();
  assert.equal(await details.locator(".pattern-card").count(), 0);
  assert.doesNotMatch(await details.textContent(), /No supported opportunity/);
  await page.unroute(patternRoute);
  await details.getByRole("button", { name: "Retry analysis", exact: true }).click();
  await details.locator(".pattern-card").first().waitFor();

  await page.route(patternRoute, async (route) => {
    if (new URL(route.request().url()).searchParams.get("view") !== "full") { await route.continue(); return; }
    const response = await route.fetch(), data = await response.json();
    delete data.view;
    await route.fulfill({ response, json: data });
  });
  await refreshDetails();
  assert.match(await details.locator(".pattern-error").textContent(), /Restart ListenFlow/);
  await page.unroute(patternRoute);
  await details.getByRole("button", { name: "Retry analysis", exact: true }).click();
  await details.locator(".pattern-card").first().waitFor();

  await page.route(patternRoute, async (route) => {
    if (new URL(route.request().url()).searchParams.get("view") !== "full") { await route.continue(); return; }
    const response = await route.fetch(), data = await response.json();
    data.transcript_fingerprint = "different-version";
    await route.fulfill({ response, json: data });
  });
  await refreshDetails();
  assert.match(await details.locator(".pattern-error").textContent(), /versions differ/);
  assert.equal(await details.locator(".pattern-card").count(), 0);
  await page.unroute(patternRoute);
  await details.getByRole("button", { name: "Retry analysis", exact: true }).click();
  await details.locator(".pattern-card").first().waitFor();

  async function editFirst(text) {
    await page.locator("#editToggle").click();
    await page.locator(".seg-text").first().fill(text);
    await page.locator("#editToggle").click();
    await page.waitForFunction(() => document.querySelector("#editToggle").textContent === "Edit");
    await page.waitForFunction(() => jobs.get(activeId).patternPages?.get(0)?.state === "done");
    await page.locator(".seg-actions button").filter({ hasText: "Patterns" }).first().click();
    await page.waitForFunction(() => jobs.get(activeId).patternDetails?.get(0)?.state === "done");
  }
  for (const [text, rule] of [["need it", "linking.c_v"], ["turn off", "linking.c_v"],
    ["see it", "linking.v_v"], ["did you", "assimilation.yod"], ["want to", "reduction.function_word"]]) {
    await editFirst(text);
    const card = details.locator('.pattern-card[data-rule-id="' + rule + '"]');
    await card.first().waitFor();
    assert.equal(await card.first().locator(".pattern-phrase").textContent(), text);
    assert.equal(await card.first().getByRole("button").textContent(), "Replay segment");
    assert.ok(await page.locator('.seg .pattern-cue[data-rule-id="' + rule + '"]').count());
  }
  await editFirst("zzqxunknown");
  assert.match(await details.textContent(), /Dictionary coverage is incomplete/);
  assert.match(await details.textContent(), /No supported opportunity/);
  await editFirst("Hello world.");
  assert.match(await details.textContent(), /Connected speech may still be present/);
  assert.doesNotMatch(await details.textContent(), /Dictionary coverage is incomplete/);
  await editFirst("🙂 Hello. Need it.");
  const unicodeUnits = page.locator(".seg").first().locator(".sentence-unit");
  assert.equal(await unicodeUnits.count(), 2);
  assert.equal(await unicodeUnits.first().locator(".pattern-cue").count(), 0);
  assert.ok(await unicodeUnits.nth(1).locator('.pattern-cue[data-rule-id="linking.c_v"]').count());
  await editFirst("Hello world.");

  let releaseOld, fetchedOld;
  const oldReady = new Promise((resolve) => { fetchedOld = resolve; });
  let deferFirst = true;
  await page.route(patternRoute, async (route) => {
    if (!deferFirst || new URL(route.request().url()).searchParams.get("view") !== "full") { await route.continue(); return; }
    deferFirst = false;
    const response = await route.fetch(); fetchedOld();
    await new Promise((resolve) => { releaseOld = resolve; });
    await route.fulfill({ response });
  });
  await page.evaluate(() => {
    const j = jobs.get(activeId); window.oldStudy = renderSentenceDetails(j, j.segments[0], 0, j.segments[0].sentenceUnits[0], true);
  });
  await oldReady;
  await editFirst("need it");
  releaseOld();
  await page.evaluate(() => window.oldStudy);
  assert.match(await details.locator(".pattern-phrase").first().textContent(), /need it/);
  await page.unroute(patternRoute);
  await editFirst("Did you get it?");
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

  // Isolated text/timing fixtures exercise cross-segment and missing-audio UI,
  // not acoustic realization or the accuracy of these synthetic timestamps.
  const seed = spawnSync(python, ["-c", `
from pathlib import Path
import shutil
import library
root = Path(${JSON.stringify(dataDir)})
segments = [
    {"text":"need", "start":0, "end":1, "words":[{"word":"need","start":0,"end":1}]},
    {"text":"it", "start":1.15, "end":2.15, "words":[{"word":"it","start":1.15,"end":2.15}]},
    {"text":"better", "start":2.15, "end":3.15, "words":[{"word":"better","start":2.15,"end":3.15}]},
    {"text":"We kept moving. Need it.", "start":4, "end":9, "words":[{"word":w,"start":4+i,"end":5+i} for i,w in enumerate(["We","kept","moving.","Need","it."])]},
]
folder = root / "uploads" / "speech-ui"
folder.mkdir(parents=True)
shutil.copyfile(Path("validation-artifacts/clear-speech.wav"), folder / "source.wav")
library.add("speech-ui", "Text and timing UI fixture", segments, media_path="speech-ui/source.wav")
library.add("speech-legacy", "Missing source UI fixture", segments)
long = []
text = "Need it. Turn off. See it. Did you want to leave? We kept moving. It is better for a moment."
from pronunciation.context import TOKEN
for i in range(1200):
    words = [{"word":m.group(),"start":i*5+j*.24,"end":i*5+(j+1)*.24} for j,m in enumerate(TOKEN.finditer(text))]
    long.append({"text":text,"start":i*5,"end":words[-1]["end"],"words":words})
library.add("speech-long", "Long transcript UI fixture", long)
`], { cwd: root, env: { ...process.env, LIBRARY_DB: path.join(dataDir, "library.db") }, encoding: "utf8", windowsHide: true });
  assert.equal(seed.status, 0, seed.stderr);
  await page.goto(base + "/?recording=speech-ui");
  await page.waitForFunction(() => jobs.get(activeId)?.patternPages?.get(0)?.state === "done");
  assert.equal(await page.locator(".pattern-word").count(), 7);
  await page.locator(".seg-actions button").filter({ hasText: "Patterns" }).nth(1).click();
  const crossCard = page.locator('.sentence-details[open] .pattern-card[data-rule-id="linking.c_v"]').filter({ hasText: "need it" });
  await crossCard.waitFor();
  await crossCard.getByRole("button", { name: "Replay phrase", exact: true }).click();
  assert.ok(await page.locator("#player").evaluate((el) => !el.paused && el.currentTime < .75));
  await page.locator("#player").evaluate((el) => el.pause());
  const multi = page.locator(".seg").nth(3);
  assert.equal(await multi.locator(".sentence-unit").count(), 2);
  const omission = multi.locator('.sentence-unit').first().locator('.pattern-cue[data-rule-id="elision.cluster_td"]');
  assert.equal(await omission.locator("s").textContent(), "t");
  assert.equal(await multi.locator('.sentence-unit').nth(1).locator('.pattern-cue[data-rule-id="elision.cluster_td"]').count(), 0);
  assert.equal(await multi.locator(".seg-text").textContent(), "We kept moving. Need it.");
  const plainExport = await (await fetch(base + "/api/jobs/speech-ui/download/txt")).text();
  assert.match(plainExport, /We kept moving/); assert.doesNotMatch(plainExport, /Possible pattern|Weak form/);
  await page.evaluate(() => {
    window.heldWord = document.querySelector(".sentence-text .w");
    const range = document.createRange(); range.selectNodeContents(window.heldWord);
    const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
  });
  await page.evaluate(() => ensurePatternPage(jobs.get(activeId), 0, true));
  assert.ok(await page.evaluate(() => heldWord === document.querySelector(".sentence-text .w")));
  assert.equal(await page.evaluate(() => getSelection().toString()), "need");
  await page.evaluate(() => getSelection().removeAllRanges());
  await page.locator("#search").fill("kept");
  assert.ok(await page.locator("mark.hit").count());
  assert.equal(await page.locator(".seg-reading:visible").count(), 0);
  await page.locator("#search").fill("");
  await omission.waitFor();
  await omission.click();
  await multi.locator(".pattern-card").first().waitFor();
  await page.screenshot({ path: path.join(dataDir, "inline-speech.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Inline pronunciation cues overflow mobile layout.");
  await page.screenshot({ path: path.join(dataDir, "inline-speech-mobile.png"), fullPage: true });
  await page.goto(base + "/?recording=speech-legacy");
  await page.waitForFunction(() => jobs.get(activeId)?.studyLoaded);
  await page.locator(".seg-actions button").filter({ hasText: "Patterns" }).nth(1).click();
  assert.ok(await page.getByRole("button", { name: "Audio unavailable", exact: true }).first().isDisabled());

  // Warm-server long-library measurement; report timings rather than assert a latency promise.
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(base);
  await page.locator("#libraryBtn").click();
  const longRequests = [], longResponses = [], bodyReads = [];
  const capture = (request) => { if (request.url().includes("/speech-long/patterns?")) longRequests.push(request.url()); };
  page.on("request", capture);
  page.on("response", (response) => {
    if (!response.url().includes("/speech-long/patterns?")) return;
    bodyReads.push(response.body().then((body) => longResponses.push({
      view: new URL(response.url()).searchParams.get("view"), bytes: body.length,
    })));
  });
  const began = Date.now();
  await page.locator(".lib-card").filter({ hasText: "Long transcript UI fixture" }).click();
  await page.locator(".pattern-cue").first().waitFor();
  const firstCuesMs = Date.now() - began;
  assert.ok(longRequests.length > 0 && longRequests.length < 10);
  assert.ok(longRequests.every((u) => new URL(u).searchParams.get("view") === "summary"));
  const clickBegan = Date.now();
  await page.locator(".pattern-cue").first().click();
  await page.locator(".sentence-details[open] .pattern-card").first().waitFor();
  const firstDetailsMs = Date.now() - clickBegan, requestsAfterDetails = longRequests.length;
  const cachedBegan = Date.now();
  await page.locator(".pattern-cue").first().click();
  await page.locator(".sentence-details[open] .pattern-card").first().waitFor();
  const cachedDetailsMs = Date.now() - cachedBegan;
  assert.equal(longRequests.length, requestsAfterDetails, "Repeated details should use the revision-scoped cache.");
  await page.locator(".seg").last().scrollIntoViewIfNeeded();
  await page.locator(".seg").last().locator(".pattern-cue").first().waitFor();
  assert.ok(longRequests.some((u) => new URL(u).searchParams.get("segment_start") === "1176"));
  await Promise.all(bodyReads);
  assert.ok(patternRequests.every((u) => {
    const q = new URL(u).searchParams;
    return q.has("segment_start") && Number(q.get("segment_limit")) <= 24 && Number(q.get("segment_limit")) >= 1;
  }), "The browser must not request full-transcript analysis.");
  const perf = { firstCuesMs, firstDetailsMs, cachedDetailsMs, patternRequests: longRequests.length,
    responseBytes: longResponses,
    segments: 1200, limits: "One warm-server synthetic-library Chrome run, not a statistical latency guarantee." };
  fs.writeFileSync(path.join(dataDir, "inline-performance.json"), JSON.stringify(perf, null, 2));
  console.log("Long-library UI measurement: " + JSON.stringify(perf));
  assert.deepEqual(errors, [], "Browser JavaScript errors");
  assert.deepEqual(network, [], "Unexpected external browser requests");
  fs.writeFileSync(path.join(dataDir, "result.json"), JSON.stringify({ passed: true, recordingId: id, browserErrors: errors, externalRequests: network }, null, 2));
  console.log("PASS: upload, real ASR, highlighting, seek, speed, replay, loop, edits, clips, inline sentence cues/IPA/possible omission, lazy explanations/evidence, bounded loading/cache, five requested phrases, analysis failure/retry/coverage/empty states, exports, actual process restart, playback, deletion, retry, desktop/mobile layout.");
  console.log("Evidence: " + dataDir);
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  await stopServer();
});
