// Static-site dashboard: all data comes from ./data/*.json, regenerated
// daily by the GitHub Actions ingestion job. No backend, no API base URL.

const state = {
  fii: [], fpi: [],
  sort: { fii: { key: "fii_per_60", dir: -1 }, fpi: { key: "fpi_pct", dir: -1 } },
};

async function loadJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function heatColor(value, max) {
  // ice-blue (cold) -> amber (hot), interpolated linearly
  const t = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  const cold = [79, 209, 232], hot = [255, 107, 53];
  const rgb = cold.map((c, i) => Math.round(c + (hot[i] - c) * t));
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function renderFII() {
  const tbody = document.getElementById("fii-tbody");
  const search = document.getElementById("fii-search").value.trim().toLowerCase();
  const minToiOn = document.getElementById("fii-min-toi").checked;
  const minGames = Math.max(1, parseInt(document.getElementById("fii-min-games").value, 10) || 1);

  let rows = state.fii.filter(r =>
    (!minToiOn || r.total_shared_toi_min >= 20) &&
    r.games >= minGames &&
    (!search || r.name.toLowerCase().includes(search) || (r.team || "").toLowerCase().includes(search))
  );

  const { key, dir } = state.sort.fii;
  rows = rows.slice().sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir);

  const max = Math.max(1, ...rows.map(r => r.fii_per_60));
  tbody.innerHTML = "";
  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;">No players match yet &mdash; check back after the next update.</td></tr>`;
    return;
  }
  rows.forEach((r, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td class="name">${escapeHtml(r.name)}</td>
      <td class="team">${escapeHtml(r.team || "\u2014")}</td>
      <td class="num"><div class="heat-cell">
        <div class="heat-bar-track"><div class="heat-bar-fill" style="width:${(r.fii_per_60 / max) * 100}%;background:${heatColor(r.fii_per_60, max)}"></div></div>
        <span class="heat-value">${r.fii_per_60.toFixed(1)}</span>
      </div></td>
      <td class="num">${r.games}</td>
      <td class="num">${r.total_shared_toi_min.toFixed(0)}</td>`;
    tr.addEventListener("click", () => openPlayerModal(r.player_id, r.name));
    tbody.appendChild(tr);
  });
}

function renderFPI() {
  const tbody = document.getElementById("fpi-tbody");
  const search = document.getElementById("fpi-search").value.trim().toLowerCase();
  const minGames = Math.max(1, parseInt(document.getElementById("fpi-min-games").value, 10) || 1);

  let rows = state.fpi.filter(r =>
    r.games >= minGames &&
    (!search || r.name.toLowerCase().includes(search) || (r.team || "").toLowerCase().includes(search))
  );
  const { key, dir } = state.sort.fpi;
  rows = rows.slice().sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir);

  tbody.innerHTML = "";
  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;">No players match yet &mdash; check back after the next update.</td></tr>`;
    return;
  }
  rows.forEach((r, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td class="name">${escapeHtml(r.name)}</td>
      <td class="team">${escapeHtml(r.team || "\u2014")}</td>
      <td class="num"><div class="heat-cell">
        <div class="heat-bar-track"><div class="heat-bar-fill" style="width:${r.fpi_pct}%;background:${heatColor(r.fpi_pct, 100)}"></div></div>
        <span class="heat-value">${r.fpi_pct.toFixed(0)}</span>
      </div></td>
      <td class="team">${escapeHtml(r.as_of_date || "")}</td>
      <td class="num">${r.games}</td>`;
    tbody.appendChild(tr);
  });
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function openPlayerModal(playerId, name) {
  const modal = document.getElementById("player-modal");
  const body = document.getElementById("modal-body");
  body.innerHTML = `<h3>${escapeHtml(name)}</h3><p style="color:var(--text-muted)">Loading&hellip;</p>`;
  modal.hidden = false;

  try {
    const detail = await loadJSON(`data/players/${playerId}.json`);
    if (!detail.fii_games || detail.fii_games.length === 0) {
      body.innerHTML = `<h3>${escapeHtml(name)}</h3><p style="color:var(--text-muted)">No game-level detail on file yet.</p>`;
      return;
    }
    const recent = detail.fii_games.slice(-5).reverse();
    body.innerHTML = `
      <h3>${escapeHtml(name)}</h3>
      <p style="color:var(--text-muted);font-family:ui-sans-serif,system-ui,sans-serif;font-size:0.85rem;">
        Most recent games, and who they fatigued most that night.
      </p>
      ${recent.map(g => `
        <div style="margin-top:1rem;padding-top:0.75rem;border-top:1px solid var(--border);">
          <div style="display:flex;justify-content:space-between;font-size:0.85rem;">
            <span>${escapeHtml(g.date)}</span>
            <span style="color:var(--ice)">FII/60: ${g.fii_per_60.toFixed(1)}</span>
          </div>
          ${g.top_matchups.map(m => `
            <div class="matchup-row">
              <span style="color:var(--text-muted)">${escapeHtml(m.opponent_name || `opponent #${m.opponent_player_id}`)} (role wt ${m.role_weight.toFixed(2)})</span>
              <span>${m.weighted_toll.toFixed(1)}</span>
            </div>`).join("")}
        </div>`).join("")}
    `;
  } catch (e) {
    body.innerHTML = `<h3>${escapeHtml(name)}</h3><p style="color:var(--hot)">Couldn't load detail: ${e.message}</p>`;
  }
}

function setupSorting() {
  document.querySelectorAll("#fii-table th[data-sort]").forEach(th => {
    th.tabIndex = 0;
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      const s = state.sort.fii;
      s.dir = s.key === key ? -s.dir : -1;
      s.key = key;
      document.querySelectorAll("#fii-table th").forEach(t => t.classList.remove("sort-active"));
      th.classList.add("sort-active");
      renderFII();
    });
  });
  document.querySelectorAll("#fpi-table th[data-sort]").forEach(th => {
    th.tabIndex = 0;
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      const s = state.sort.fpi;
      s.dir = s.key === key ? -s.dir : -1;
      s.key = key;
      document.querySelectorAll("#fpi-table th").forEach(t => t.classList.remove("sort-active"));
      th.classList.add("sort-active");
      renderFPI();
    });
  });
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => { t.classList.remove("active"); t.setAttribute("aria-selected", "false"); });
      document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
    });
  });
}

function setupModal() {
  const modal = document.getElementById("player-modal");
  document.getElementById("modal-close").addEventListener("click", () => modal.hidden = true);
  modal.addEventListener("click", e => { if (e.target === modal) modal.hidden = true; });
  document.addEventListener("keydown", e => { if (e.key === "Escape") modal.hidden = true; });
}

async function loadStatus() {
  const el = document.getElementById("status-text");
  const strip = document.getElementById("status-strip");
  try {
    const status = await loadJSON("data/status.json");
    const last = new Date(status.last_run_utc);
    const ageHours = Math.round((Date.now() - last.getTime()) / 3600000);
    if (status.error_count_recent > 0) {
      strip.classList.add("error");
      el.textContent = `Last update ${ageHours}h ago \u2014 ${status.error_count_recent} game(s) failed to ingest recently.`;
    } else {
      el.textContent = `Last update ${ageHours}h ago \u2014 pipeline healthy.`;
    }
  } catch (e) {
    strip.classList.add("error");
    el.textContent = "Status unavailable.";
  }
}

async function init() {
  setupTabs();
  setupSorting();
  setupModal();
  document.getElementById("fii-search").addEventListener("input", renderFII);
  document.getElementById("fii-min-toi").addEventListener("change", renderFII);
  document.getElementById("fii-min-games").addEventListener("input", renderFII);
  document.getElementById("fpi-search").addEventListener("input", renderFPI);
  document.getElementById("fpi-min-games").addEventListener("input", renderFPI);

  try {
    const [fii, fpi] = await Promise.all([
      loadJSON("data/leaderboard_fii.json"),
      loadJSON("data/leaderboard_fpi.json"),
    ]);
    state.fii = fii;
    state.fpi = fpi;
  } catch (e) {
    document.getElementById("fii-tbody").innerHTML =
      `<tr><td colspan="6" style="text-align:center;color:var(--hot);padding:2rem;">Data not available yet \u2014 the first ingestion run hasn't completed.</td></tr>`;
  }
  renderFII();
  renderFPI();
  loadStatus();
}

init();
