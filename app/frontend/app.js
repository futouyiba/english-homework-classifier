const $ = (id) => document.getElementById(id);
let mappingsCache = null;
let inboxRowsCache = [];
let lastDailyBuild = null;

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

async function api(url, options = {}) {
  const resp = await fetch(url, options);
  const text = await resp.text();
  let body = text;
  try {
    body = JSON.parse(text);
  } catch {}
  if (!resp.ok) {
    const msg = typeof body === "object" ? pretty(body) : String(body);
    throw new Error(`${resp.status} ${resp.statusText}\n${msg}`);
  }
  return body;
}

async function loadMappings() {
  if (mappingsCache) return mappingsCache;
  mappingsCache = await api("/api/config/mappings");
  return mappingsCache;
}

function fillRelabelIndexes(itemType) {
  const indexSelect = $("relabel-index");
  indexSelect.innerHTML = "";
  const fallbackMax = itemType === "VOCAB" ? 17 : itemType === "SENTENCE" ? 15 : 6;
  const maxIndex = Number(mappingsCache?.[itemType]?.max_index || fallbackMax);
  for (let i = 1; i <= maxIndex; i += 1) {
    const opt = document.createElement("option");
    opt.value = String(i);
    opt.textContent = String(i);
    indexSelect.appendChild(opt);
  }
}

function applyRelabelTitles(itemType, index) {
  const meta = mappingsCache?.[itemType]?.items?.[String(index)] || {};
  $("relabel-title-zh").value = meta.title_zh || "";
  $("relabel-title-en").value = meta.title_en || "";
}

function resetRelabelForm() {
  $("relabel-id").value = "";
  $("relabel-type").value = "VOCAB";
  fillRelabelIndexes("VOCAB");
  $("relabel-index").value = "1";
  applyRelabelTitles("VOCAB", 1);
  $("relabel-audio").removeAttribute("src");
  $("relabel-audio").load();
  $("relabel-meta").textContent = "";
}

function showRelabelMeta(row) {
  $("relabel-meta").textContent = pretty({
    id: row.id,
    src_path: row.src_path,
    asr_engine: row?.asr?.engine,
    tag: row.tag,
    needs_review: row.needs_review,
  });
  if (row.src_path) {
    $("relabel-audio").src = `/api/file?path=${encodeURIComponent(row.src_path)}`;
  } else {
    $("relabel-audio").removeAttribute("src");
    $("relabel-audio").load();
  }
}

function bindTabs() {
  const buttons = Array.from(document.querySelectorAll(".tab-btn"));
  const panels = {
    inbox: $("tab-inbox"),
    library: $("tab-library"),
    daily: $("tab-daily"),
    asr: $("tab-asr"),
    source: $("tab-source"),
  };
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("is-active"));
      Object.values(panels).forEach((p) => p.classList.remove("is-active"));
      btn.classList.add("is-active");
      panels[btn.dataset.tab].classList.add("is-active");
    });
  });
}

async function refreshInbox() {
  const rows = await api("/api/inbox/items");
  inboxRowsCache = rows;
  const onlyReview = $("inbox-only-review")?.checked;
  const filterType = $("inbox-filter-type")?.value || "ALL";
  const filterIndexRaw = ($("inbox-filter-index")?.value || "").trim();
  const filterIndex = filterIndexRaw ? Number(filterIndexRaw) : null;

  const filteredRows = rows.filter((r) => {
    if (onlyReview && !r.needs_review) return false;
    if (filterType !== "ALL" && r?.tag?.type !== filterType) return false;
    if (filterIndex && Number(r?.tag?.index || 0) !== filterIndex) return false;
    return true;
  });

  const reviewCount = rows.filter((r) => r.needs_review).length;
  const archivedCount = rows.filter((r) => Boolean(r.library_path)).length;
  $("stat-total").textContent = `总数: ${rows.length}`;
  $("stat-review").textContent = `待复核: ${reviewCount}`;
  $("stat-archived").textContent = `已落库: ${archivedCount}`;

  const tbody = $("inbox-table");
  tbody.innerHTML = "";
  for (const row of filteredRows) {
    const tr = document.createElement("tr");
    const title = `${row?.tag?.title_zh || ""} / ${row?.tag?.title_en || ""}`;
    const signals = row?.tag?.signals || {};
    const signalPreview = (signals.hit_keywords || []).slice(0, 3);
    const signalHtml = signalPreview.length
      ? signalPreview.map((x) => `<span class="signal-chip">${x}</span>`).join("")
      : '<span class="signal-chip">无</span>';
    tr.innerHTML = `
      <td>${row.created_at || ""}</td>
      <td>${row?.tag?.type || ""}</td>
      <td>${row?.tag?.index || ""}</td>
      <td>${title}</td>
      <td>${(row?.tag?.confidence ?? 0).toFixed ? row.tag.confidence.toFixed(2) : row?.tag?.confidence || ""}</td>
      <td class="${row.needs_review ? "flag-yes" : ""}">${row.needs_review ? "是" : "否"}</td>
      <td>${row.library_path || ""}</td>
      <td>${row.src_path ? `<a href="/api/file?path=${encodeURIComponent(row.src_path)}" target="_blank" rel="noopener">源文件</a>` : "-"}</td>
      <td>${signalHtml}</td>
      <td>${row.needs_review ? `<button class="alt mini-btn" data-action="pick-relabel" data-id="${row.id}" data-type="${row?.tag?.type || ""}" data-index="${row?.tag?.index || ""}">手动修正</button>` : "-"}</td>
    `;
    tbody.appendChild(tr);
  }
}

function initInbox() {
  $("btn-upload").addEventListener("click", async () => {
    const files = $("inbox-files").files;
    if (!files || !files.length) {
      $("inbox-log").textContent = "请先选择音频文件。";
      return;
    }
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    try {
      const data = await api("/api/inbox/upload", { method: "POST", body: fd });
      $("inbox-log").textContent = pretty(data);
      await refreshInbox();
    } catch (e) {
      $("inbox-log").textContent = String(e);
    }
  });

  $("btn-scan").addEventListener("click", async () => {
    try {
      const data = await api("/api/inbox/scan", { method: "POST" });
      $("inbox-log").textContent = pretty(data);
      await refreshInbox();
    } catch (e) {
      $("inbox-log").textContent = String(e);
    }
  });

  $("btn-refresh").addEventListener("click", async () => {
    try {
      await refreshInbox();
      $("inbox-log").textContent = "列表已刷新。";
    } catch (e) {
      $("inbox-log").textContent = String(e);
    }
  });

  $("inbox-only-review").addEventListener("change", async () => {
    try {
      await refreshInbox();
    } catch (e) {
      $("inbox-log").textContent = String(e);
    }
  });

  $("inbox-filter-type").addEventListener("change", async () => {
    try {
      await refreshInbox();
    } catch (e) {
      $("inbox-log").textContent = String(e);
    }
  });

  $("inbox-filter-index").addEventListener("input", async () => {
    try {
      await refreshInbox();
    } catch (e) {
      $("inbox-log").textContent = String(e);
    }
  });

  $("inbox-table").addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches("button[data-action='pick-relabel']")) return;

    const itemId = target.dataset.id || "";
    const itemType = target.dataset.type || "VOCAB";
    const index = Number(target.dataset.index || "1");
    const row = inboxRowsCache.find((x) => x.id === itemId);

    $("relabel-id").value = itemId;
    $("relabel-type").value = itemType;
    fillRelabelIndexes(itemType);
    $("relabel-index").value = String(index);
    applyRelabelTitles(itemType, index);
    if (row) showRelabelMeta(row);
    $("inbox-log").textContent = `已选择待修正条目：${itemId}`;
  });

  $("relabel-type").addEventListener("change", () => {
    const itemType = $("relabel-type").value;
    fillRelabelIndexes(itemType);
    $("relabel-index").value = "1";
    applyRelabelTitles(itemType, 1);
  });

  $("relabel-index").addEventListener("change", () => {
    const itemType = $("relabel-type").value;
    const index = Number($("relabel-index").value || "1");
    applyRelabelTitles(itemType, index);
  });

  $("btn-relabel-clear").addEventListener("click", () => {
    resetRelabelForm();
    $("inbox-log").textContent = "修正表单已清空。";
  });

  $("btn-relabel").addEventListener("click", async () => {
    const id = $("relabel-id").value.trim();
    if (!id) {
      $("inbox-log").textContent = "请先在列表中选择待修正条目。";
      return;
    }
    const payload = {
      id,
      type: $("relabel-type").value,
      index: Number($("relabel-index").value || "1"),
      title_zh: $("relabel-title-zh").value.trim(),
      title_en: $("relabel-title-en").value.trim(),
    };
    try {
      const data = await api("/api/audio/relabel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      $("inbox-log").textContent = pretty(data);
      resetRelabelForm();
      await refreshInbox();
      await refreshLibrary();
    } catch (e) {
      $("inbox-log").textContent = String(e);
    }
  });
}

function initDaily() {
  const date = new Date().toISOString().slice(0, 10);
  $("daily-date").value = date;
  $("daily-template").addEventListener("change", (e) => {
    $("daily-cmd").value = e.target.value || "";
  });

  $("btn-parse").addEventListener("click", async () => {
    const text = $("daily-cmd").value.trim();
    if (!text) {
      $("daily-needs").textContent = "请先输入老师指令。";
      return;
    }
    try {
      const data = await api("/api/teacher/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      $("daily-needs").textContent = pretty(data);
    } catch (e) {
      $("daily-needs").textContent = String(e);
    }
  });

  $("btn-build").addEventListener("click", async () => {
    const dateValue = $("daily-date").value;
    const cmd = $("daily-cmd").value.trim();
    if (!cmd) {
      $("daily-result").textContent = "请先输入老师指令。";
      return;
    }
    try {
      const parsed = await api("/api/teacher/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: cmd }),
      });
      const data = await api("/api/daily/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date: dateValue,
          teacher_cmd: cmd,
          needs: parsed.needs,
        }),
      });
      $("daily-needs").textContent = pretty(parsed);
      $("daily-result").textContent = pretty(data);
      lastDailyBuild = data;
      if (data.report_path) {
        try {
          const report = await api(`/api/text?path=${encodeURIComponent(data.report_path)}`);
          $("daily-report").textContent = report.text || "";
        } catch (e) {
          $("daily-report").textContent = String(e);
        }
      }
    } catch (e) {
      $("daily-result").textContent = String(e);
    }
  });

  $("btn-load-report").addEventListener("click", async () => {
    const reportPath = lastDailyBuild?.report_path;
    if (!reportPath) {
      $("daily-report").textContent = "请先执行“生成 Daily”。";
      return;
    }
    try {
      const report = await api(`/api/text?path=${encodeURIComponent(reportPath)}`);
      $("daily-report").textContent = report.text || "";
    } catch (e) {
      $("daily-report").textContent = String(e);
    }
  });

  $("btn-open-daily").addEventListener("click", async () => {
    const dailyDir = lastDailyBuild?.daily_dir;
    if (!dailyDir) {
      $("daily-result").textContent = "请先执行“生成 Daily”。";
      return;
    }
    try {
      const data = await api(`/api/open-folder?path=${encodeURIComponent(dailyDir)}`, { method: "POST" });
      $("daily-result").textContent = `${$("daily-result").textContent}\n\n[打开目录] ${pretty(data)}`;
    } catch (e) {
      $("daily-result").textContent = String(e);
    }
  });
}

async function refreshLibrary() {
  const type = $("library-type").value;
  const data = await api("/api/library/summary");
  const rows = type === "ALL" ? data : data.filter((x) => x.type === type);
  const tbody = $("library-table");
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    const title = `${row.title_zh || ""} / ${row.title_en || ""}`;
    tr.innerHTML = `
      <td>${row.type}</td>
      <td>${row.index}</td>
      <td>${title}</td>
      <td>${row.take_count}</td>
      <td>${row.latest_time || "-"}</td>
      <td><button class="alt mini-btn" data-type="${row.type}" data-index="${row.index}">查看 takes</button></td>
    `;
    tbody.appendChild(tr);
  }
}

function renderLibraryPlayers(detail) {
  const host = $("library-player-list");
  host.innerHTML = "";
  const takes = Array.isArray(detail?.takes) ? detail.takes : [];
  if (!takes.length) {
    host.innerHTML = '<p class="hint">该条目暂无可播放 take。</p>';
    return;
  }
  for (const take of takes) {
    const item = document.createElement("div");
    item.className = "player-item";
    const p = document.createElement("p");
    p.textContent = `${take.name || "unknown"}  (${take.path || ""})`;
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = `/api/file?path=${encodeURIComponent(take.path || "")}`;
    item.appendChild(p);
    item.appendChild(audio);
    host.appendChild(item);
  }
}

function initLibrary() {
  $("btn-library-refresh").addEventListener("click", async () => {
    try {
      await refreshLibrary();
      $("library-log").textContent = "素材统计已刷新。";
    } catch (e) {
      $("library-log").textContent = String(e);
    }
  });

  $("library-type").addEventListener("change", async () => {
    try {
      await refreshLibrary();
    } catch (e) {
      $("library-log").textContent = String(e);
    }
  });

  $("library-table").addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches("button[data-type]")) return;
    const itemType = target.dataset.type;
    const index = target.dataset.index;
    if (!itemType || !index) return;
    try {
      const detail = await api(`/api/library/takes?type=${encodeURIComponent(itemType)}&index=${index}`);
      renderLibraryPlayers(detail);
      $("library-detail").textContent = pretty(detail);
    } catch (e) {
      $("library-player-list").innerHTML = "";
      $("library-detail").textContent = String(e);
    }
  });
}

function initAsr() {
  $("btn-asr-test").addEventListener("click", async () => {
    const file = $("asr-file").files?.[0];
    if (!file) {
      $("asr-result").textContent = "请先选择音频文件。";
      return;
    }
    const scope = $("asr-scope").value;
    const windowSec = Number($("asr-window").value || 20);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const data = await api(`/api/asr/test?scope=${encodeURIComponent(scope)}&tag_window_sec=${windowSec}`, {
        method: "POST",
        body: fd,
      });
      $("asr-result").textContent = pretty(data);
    } catch (e) {
      $("asr-result").textContent = String(e);
    }
  });

  $("btn-health").addEventListener("click", async () => {
    try {
      const data = await api("/api/health");
      $("health-result").textContent = pretty(data);
    } catch (e) {
      $("health-result").textContent = String(e);
    }
  });
}

async function refreshSourceFiles() {
  const data = await api("/api/structured/list");
  const select = $("source-file");
  select.innerHTML = "";
  for (const name of data.files || []) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  }
}

function initSource() {
  $("btn-source-refresh").addEventListener("click", async () => {
    try {
      await refreshSourceFiles();
      $("source-log").textContent = "文件列表已刷新。";
    } catch (e) {
      $("source-log").textContent = String(e);
    }
  });

  $("btn-source-read").addEventListener("click", async () => {
    const name = $("source-file").value;
    if (!name) {
      $("source-log").textContent = "请先选择文件。";
      return;
    }
    try {
      const data = await api(`/api/structured/read?path=${encodeURIComponent(name)}`);
      $("source-content").textContent = pretty(data.data ?? data.text ?? data);
      $("source-log").textContent = `已读取: ${name}`;
    } catch (e) {
      $("source-log").textContent = String(e);
    }
  });

  $("btn-apply-seed").addEventListener("click", async () => {
    try {
      const data = await api("/api/config/apply-seed", { method: "POST" });
      mappingsCache = null;
      await loadMappings();
      $("source-log").textContent = `seed 已应用: ${pretty(data)}`;
    } catch (e) {
      $("source-log").textContent = String(e);
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  bindTabs();
  try {
    await loadMappings();
  } catch (e) {
    $("inbox-log").textContent = `加载 mappings 失败，将使用默认索引范围。\n${String(e)}`;
  }
  initInbox();
  initLibrary();
  initDaily();
  initAsr();
  initSource();
  resetRelabelForm();
  try {
    await refreshInbox();
    await refreshLibrary();
    await refreshSourceFiles();
  } catch (e) {
    $("inbox-log").textContent = String(e);
  }
});
