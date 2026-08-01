/* ── MC Panel — panel.js ──────────────────────── */

const socket = io();
let serverOnline = false;
let startTime = null;
let uptimeInterval = null;
let cmdHistory = [];
let historyIdx = -1;

/* ── WebSocket events ───────────────────────── */
socket.on("connect", () => {
  addLog("ok", "[Panel]", "WebSocket connected.");
});

socket.on("disconnect", () => {
  addLog("error", "[Panel]", "WebSocket disconnected.");
  setOnline(false);
});

socket.on("stats", (data) => {
  updateStats(data);
});

socket.on("log", (entry) => {
  const cls = entry.ok ? "ok" : "error";
  addLog(cls, "[RCON ›]", entry.cmd);
  addLog(entry.ok ? "info" : "error", "[resp]", entry.response);
});

/* ── Stat updates ───────────────────────────── */
function updateStats(data) {
  const online = data.online;
  setOnline(online);

  if (!startTime && online) {
    startTime = Date.now();
    startUptimeClock();
  }
  if (!online) {
    startTime = null;
    if (uptimeInterval) { clearInterval(uptimeInterval); uptimeInterval = null; }
    document.getElementById("uptimeLabel").textContent = "offline";
  }

  // Players
  const pc = data.player_count ?? 0;
  setText("statPlayers", pc);
  setBar("barPlayers", (pc / 20) * 100);

  // TPS
  const tps = data.tps;
  if (tps !== null && tps !== undefined) {
    setText("statTps", tps.toFixed(1));
    const tpsPct = Math.min((tps / 20) * 100, 100);
    setBar("barTps", tpsPct);
    document.getElementById("barTps").className = "stat-fill " + (tps > 18 ? "green" : tps > 15 ? "amber" : "red");
  } else {
    setText("statTps", "N/A");
    setBar("barTps", 0);
  }

  // CPU
  const sys = data.system || {};
  if (sys.cpu !== undefined) {
    setText("statCpu", sys.cpu + "%");
    setBar("barCpu", sys.cpu);
    document.getElementById("barCpu").className = "stat-fill " + (sys.cpu < 50 ? "green" : sys.cpu < 80 ? "amber" : "red");
  }

  // RAM
  if (sys.ram_used !== undefined) {
    setText("statRam", sys.ram_used + "G");
    setBar("barRam", sys.ram_percent || 0);
    document.getElementById("subRam").textContent = `${sys.ram_used} / ${sys.ram_total} GB`;
    document.getElementById("barRam").className = "stat-fill " + (sys.ram_percent < 60 ? "green" : sys.ram_percent < 80 ? "amber" : "red");
  }

  // Online players list
  renderPlayers(data.players || []);
  document.getElementById("playersCount").textContent = pc;
}

function setOnline(online) {
  serverOnline = online;
  const badge = document.getElementById("statusBadge");
  const dot = document.getElementById("rconDot");
  const label = document.getElementById("rconLabel");

  badge.className = "badge " + (online ? "online" : "offline");
  document.getElementById("statusText").textContent = online ? "Online" : "Offline";
  dot.className = "rcon-dot " + (online ? "online" : "offline");
  label.textContent = online ? "RCON connected" : "RCON disconnected";
}

function startUptimeClock() {
  if (uptimeInterval) clearInterval(uptimeInterval);
  uptimeInterval = setInterval(() => {
    if (!startTime) return;
    const secs = Math.floor((Date.now() - startTime) / 1000);
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    document.getElementById("uptimeLabel").textContent =
      `uptime ${pad(h)}:${pad(m)}:${pad(s)}`;
  }, 1000);
}

function pad(n) { return String(n).padStart(2, "0"); }

function renderPlayers(players) {
  const table = document.getElementById("playerTable");
  if (!players.length) {
    table.innerHTML = '<div class="empty-state">No players online</div>';
    return;
  }
  table.innerHTML = players.map(p => `
    <div class="player-row">
      <span class="player-name">${escHtml(p.name)}</span>
      <span class="player-ping">${p.ping !== null && p.ping !== undefined ? p.ping + "ms" : "—"}</span>
      <span></span>
      <button class="player-act" onclick="kickPlayer('${escHtml(p.name)}')">Kick</button>
      <button class="player-act" onclick="banPlayer('${escHtml(p.name)}')">Ban</button>
    </div>
  `).join("");
}

/* ── Log console ────────────────────────────── */
function addLog(cls, tag, msg) {
  const box = document.getElementById("logBox");
  const line = document.createElement("span");
  const now = new Date();
  const hms = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  line.className = "log-line " + cls;
  line.textContent = `[${hms}] ${tag} ${msg}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function clearLog() {
  document.getElementById("logBox").innerHTML = "";
  addLog("gray", "[Panel]", "Console cleared.");
}

/* ── API helpers ────────────────────────────── */
async function post(url, body = {}) {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await r.json();
  } catch (e) {
    return { ok: false, response: "Network error: " + e.message };
  }
}

async function rconCmd(cmd) {
  if (!cmd) return;
  addLog("cmd", "[›]", cmd);
  const res = await post("/api/command", { command: cmd });
  addLog(res.ok ? "ok" : "error", "[resp]", res.response);
  return res;
}

/* ── Command input ──────────────────────────── */
function sendCommand() {
  const inp = document.getElementById("cmdInput");
  const cmd = inp.value.trim();
  if (!cmd) return;
  cmdHistory.unshift(cmd);
  historyIdx = -1;
  inp.value = "";
  rconCmd(cmd);
}

document.addEventListener("DOMContentLoaded", () => {
  const inp = document.getElementById("cmdInput");
  inp.addEventListener("keydown", (e) => {
    if (e.key === "ArrowUp") {
      historyIdx = Math.min(historyIdx + 1, cmdHistory.length - 1);
      inp.value = cmdHistory[historyIdx] || "";
      e.preventDefault();
    } else if (e.key === "ArrowDown") {
      historyIdx = Math.max(historyIdx - 1, -1);
      inp.value = historyIdx === -1 ? "" : cmdHistory[historyIdx];
      e.preventDefault();
    }
  });
});

/* ── Quick actions ──────────────────────────── */
async function quickAction(action) {
  switch (action) {
    case "save":        return rconCmd("save-all");
    case "time-day":    return rconCmd("time set day");
    case "time-night":  return rconCmd("time set night");
    case "weather-clear": return rconCmd("weather clear");
    case "weather-rain":  return rconCmd("weather rain");
    case "kickall": {
      const reason = prompt("Kick reason:", "Server restart");
      if (reason === null) return;
      return rconCmd(`kick @a ${reason}`);
    }
  }
}

async function sendSay() {
  const inp = document.getElementById("sayInput");
  const msg = inp.value.trim();
  if (!msg) return;
  const res = await post("/api/say", { message: msg });
  addLog(res.ok ? "ok" : "error", "[say]", res.response);
  inp.value = "";
}

async function setGamemode(mode) {
  return rconCmd(`gamemode ${mode} @a`);
}

async function setTime(value) {
  const res = await post("/api/time", { value });
  addLog(res.ok ? "ok" : "error", "[time]", res.response);
}

async function setWeather(value) {
  const res = await post("/api/weather", { value });
  addLog(res.ok ? "ok" : "error", "[weather]", res.response);
}

async function sendWorldCmd() {
  const inp = document.getElementById("worldCmdInput");
  const cmd = inp.value.trim();
  if (!cmd) return;
  const res = await rconCmd(cmd);
  const el = document.getElementById("worldCmdResult");
  el.style.display = "block";
  el.className = "log-entry " + (res && res.ok ? "ok" : "error");
  el.textContent = res ? res.response : "No response";
}

/* ── Player actions ─────────────────────────── */
async function kickPlayer(name) {
  const reason = prompt(`Reason for kicking ${name}:`, "Kicked by admin");
  if (reason === null) return;
  const res = await post("/api/kick", { player: name, reason });
  addLog(res.ok ? "ok" : "error", "[kick]", `${name}: ${res.response}`);
}

async function banPlayer(name) {
  if (!confirm(`Ban ${name}?`)) return;
  const reason = prompt("Ban reason:", "Banned by admin");
  if (reason === null) return;
  const res = await post("/api/ban", { player: name, reason });
  addLog(res.ok ? "ok" : "error", "[ban]", `${name}: ${res.response}`);
}

/* ── Whitelist ──────────────────────────────── */
async function wlAdd() {
  const name = document.getElementById("wlInput").value.trim();
  if (!name) return;
  const res = await post("/api/whitelist/add", { player: name });
  showWlResult(res);
}

async function wlRemove() {
  const name = document.getElementById("wlInput").value.trim();
  if (!name) return;
  const res = await post("/api/whitelist/remove", { player: name });
  showWlResult(res);
}

function showWlResult(res) {
  const el = document.getElementById("wlResult");
  el.style.display = "block";
  el.className = "log-entry " + (res.ok ? "ok" : "error");
  el.textContent = res.response;
}

/* ── Navigation ─────────────────────────────── */
document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const sec = btn.dataset.section;
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("sec-" + sec).classList.add("active");
  });
});

/* ── Utils ──────────────────────────────────── */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setBar(id, pct) {
  const el = document.getElementById(id);
  if (el) el.style.width = Math.min(Math.max(pct, 0), 100).toFixed(1) + "%";
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

addLog("gray", "[Panel]", "Connecting to server...");

/* ── Day / Night Theme ───────────────────────── */
(function initTheme() {
  const toggle = document.getElementById("themeToggle");
  const saved = localStorage.getItem("mcpanel-theme") || "night";

  function applyTheme(theme) {
    if (theme === "day") {
      document.documentElement.setAttribute("data-theme", "day");
      toggle.checked = true;
    } else {
      document.documentElement.removeAttribute("data-theme");
      toggle.checked = false;
    }
  }

  applyTheme(saved);

  toggle.addEventListener("change", () => {
    const theme = toggle.checked ? "day" : "night";
    applyTheme(theme);
    localStorage.setItem("mcpanel-theme", theme);
    addLog("gray", "[Panel]", theme === "day" ? "Day mode activated." : "Night mode activated.");
  });
})();