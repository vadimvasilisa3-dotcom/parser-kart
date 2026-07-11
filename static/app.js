let currentJobId = null;
let pollTimer = null;

function formatApiError(payload, fallback) {
  if (!payload) return fallback;
  const detail = payload.detail ?? payload.message ?? payload;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const field = Array.isArray(item.loc) ? item.loc.filter((x) => x !== "body").join(".") : "";
        const msg = item.msg || item.message || JSON.stringify(item);
        return field ? `${field}: ${msg}` : msg;
      })
      .join("\n");
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch (_) {
      return fallback;
    }
  }
  return String(detail);
}

function readInt(id, fallback, min = 0, max = 9999) {
  const raw = document.getElementById(id)?.value;
  const n = parseInt(String(raw ?? "").trim(), 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

const citySelect = document.getElementById("city");
const cityCustom = document.getElementById("city_custom");

async function loadCities() {
  try {
    const res = await fetch("/cities.json");
    const cities = (await res.json()).sort((a, b) => a.localeCompare(b, "ru"));
    cities.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      citySelect.appendChild(opt);
    });
    const other = document.createElement("option");
    other.value = "__other__";
    other.textContent = "Другой город…";
    citySelect.appendChild(other);
  } catch (_) {
    const other = document.createElement("option");
    other.value = "__other__";
    other.textContent = "Другой город…";
    citySelect.appendChild(other);
  }
}

function getCityValue() {
  if (citySelect.value === "__other__") {
    return cityCustom.value.trim() || null;
  }
  return citySelect.value || null;
}

citySelect.addEventListener("change", () => {
  const isOther = citySelect.value === "__other__";
  cityCustom.classList.toggle("hidden", !isOther);
  if (isOther) cityCustom.focus();
  refreshCollectedCount();
});

document.getElementById("category").addEventListener("change", refreshCollectedCount);
document.getElementById("custom_query").addEventListener("input", debounce(refreshCollectedCount, 400));
cityCustom.addEventListener("input", debounce(refreshCollectedCount, 400));

document.querySelectorAll(".chip.preset").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.getElementById("max_results").value = chip.dataset.n;
  });
});

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

async function refreshCollectedCount() {
  const hint = document.getElementById("collected-hint");
  const countEl = document.getElementById("collected-count");
  const category = document.getElementById("category").value || null;
  const city = getCityValue();
  const custom_query = document.getElementById("custom_query").value.trim() || null;
  if (!category && !city && !custom_query) {
    hint.classList.add("hidden");
    return;
  }
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (city) params.set("city", city);
  if (custom_query) params.set("custom_query", custom_query);
  try {
    const res = await fetch(`/api/collected/count?${params}`);
    if (!res.ok) return;
    const data = await res.json();
    countEl.textContent = data.count || 0;
    hint.classList.toggle("hidden", false);
  } catch (_) {
    hint.classList.add("hidden");
  }
}

loadCities().then(refreshCollectedCount);

const tabs = document.querySelectorAll(".tab");
const panels = {
  search: document.getElementById("panel-search"),
  results: document.getElementById("panel-results"),
  history: document.getElementById("panel-history"),
};

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    Object.values(panels).forEach((p) => p.classList.remove("active"));
    panels[tab.dataset.tab].classList.add("active");
    if (tab.dataset.tab === "history") loadHistory();
  });
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.getElementById("custom_query").value = chip.dataset.q;
  });
});

document.querySelectorAll(".chip.filter-preset").forEach((chip) => {
  chip.addEventListener("click", () => {
    if (chip.dataset.preset === "leads") {
      ["filter_no_website", "filter_no_photos", "filter_no_reviews", "filter_no_menu"].forEach((id) => {
        document.getElementById(id).checked = true;
      });
      document.getElementById("filter_mode").value = "any";
    }
  });
});

function looksLikeOrgUrl(value) {
  const s = String(value || "").trim();
  if (!s) return false;
  return /yandex\.(ru|com)\/maps\/org\//i.test(s)
    || /yandex\.(ru|com)\/maps\/-\//i.test(s)
    || /[?&]oid=\d+/i.test(s);
}

async function startJobByUrl(orgUrl) {
  const res = await fetch("/api/jobs/by-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ org_url: orgUrl.trim(), ...scrapeOptionsFromForm() }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(formatApiError(err, "Не удалось запустить сбор по ссылке"));
    return false;
  }
  const data = await res.json();
  currentJobId = data.job_id;
  hideDownloads();
  document.getElementById("job-panel").classList.remove("hidden");
  startPolling();
  return true;
}

document.getElementById("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const customQuery = document.getElementById("custom_query").value.trim();
  if (looksLikeOrgUrl(customQuery)) {
    document.getElementById("org_url").value = customQuery;
    const ok = await startJobByUrl(customQuery);
    if (ok) {
      alert("Обнаружена ссылка на карточку — запущен сбор по ссылке (не поиск по тексту).");
    }
    return;
  }
  const filterIds = [
    "filter_no_website",
    "filter_no_photos",
    "filter_no_reviews",
    "filter_no_menu",
    "filter_no_social",
    "filter_no_phone",
  ];
  const filtersOn = filterIds.some((id) => document.getElementById(id).checked);
  if (filtersOn) {
    const mode = document.getElementById("filter_mode").value;
    const modeText =
      mode === "all"
        ? "должны отсутствовать ВСЕ отмеченные поля сразу"
        : "достаточно отсутствия ХОТЯ БЫ ОДНОГО отмеченного поля";
    const ok = confirm(
      `Фильтрация выгрузки: ${modeText}.\n\nПример (ИЛИ): нет отзывов, но есть сайт и фото — организация попадёт в Excel.\n\nПродолжить?`
    );
    if (!ok) return;
  }
  const body = {
    category: document.getElementById("category").value || null,
    city: getCityValue(),
    custom_query: document.getElementById("custom_query").value || null,
    max_results: Number(document.getElementById("max_results").value || 10),
    scrape_photos: document.getElementById("scrape_photos").checked,
    scrape_reviews: document.getElementById("scrape_reviews").checked,
    scrape_menu: document.getElementById("scrape_menu").checked,
    max_photos: Number(document.getElementById("max_photos").value || 10),
    max_reviews: Number(document.getElementById("max_reviews").value || 15),
    max_menu_items: Number(document.getElementById("max_menu_items").value || 100),
    filter_no_website: document.getElementById("filter_no_website").checked,
    filter_no_photos: document.getElementById("filter_no_photos").checked,
    filter_no_reviews: document.getElementById("filter_no_reviews").checked,
    filter_no_menu: document.getElementById("filter_no_menu").checked,
    filter_no_social: document.getElementById("filter_no_social").checked,
    filter_no_phone: document.getElementById("filter_no_phone").checked,
    filter_mode: document.getElementById("filter_mode").value,
    dedupe: document.getElementById("dedupe").checked,
  };

  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(formatApiError(err, "Не удалось запустить сбор"));
    return;
  }
  const data = await res.json();
  currentJobId = data.job_id;
  hideDownloads();
  document.getElementById("job-panel").classList.remove("hidden");
  startPolling();
});

function scrapeOptionsFromForm() {
  return {
    scrape_photos: document.getElementById("scrape_photos").checked,
    scrape_reviews: document.getElementById("scrape_reviews").checked,
    scrape_menu: document.getElementById("scrape_menu").checked,
    max_photos: readInt("max_photos", 10, 1, 10),
    max_reviews: readInt("max_reviews", 15, 0, 50),
    max_menu_items: readInt("max_menu_items", 100, 0, 200),
  };
}

document.getElementById("url-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const org_url = document.getElementById("org_url").value.trim();
  if (!org_url) {
    alert("Вставьте ссылку на карточку Яндекс.Карт");
    return;
  }
  await startJobByUrl(org_url);
});

document.getElementById("org_url").addEventListener("paste", (e) => {
  const text = (e.clipboardData || window.clipboardData)?.getData("text") || "";
  if (looksLikeOrgUrl(text)) {
    setTimeout(() => {
      document.getElementById("org_url").value = text.trim();
    }, 0);
  }
});

document.getElementById("custom_query").addEventListener("paste", (e) => {
  const text = (e.clipboardData || window.clipboardData)?.getData("text") || "";
  if (looksLikeOrgUrl(text)) {
    setTimeout(() => {
      document.getElementById("org_url").value = text.trim();
      document.getElementById("custom_query").value = "";
    }, 0);
  }
});

document.getElementById("job-close").addEventListener("click", () => {
  document.getElementById("job-panel").classList.add("hidden");
});

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(refreshJob, 1500);
  refreshJob();
}

async function refreshJob() {
  if (!currentJobId) return;
  const res = await fetch(`/api/jobs/${currentJobId}`);
  if (!res.ok) return;
  const job = await res.json();

  const title =
    job.query && String(job.query).includes("/maps/org/")
      ? "Сбор по ссылке на карточку"
      : job.category && job.city
        ? `Сбор: «${job.category} ${job.city}»`
        : `Сбор: «${job.query || "запрос"}»`;
  document.getElementById("job-title").textContent = title;
  document.getElementById("job-found").textContent = job.found || 0;
  const processed = (job.found || 0) + (job.skipped || 0) || job.total || 0;
  document.getElementById("job-processed").textContent = processed;
  const skippedWrap = document.getElementById("job-skipped-wrap");
  const skipped = job.skipped || 0;
  if (skipped > 0) {
    skippedWrap.classList.remove("hidden");
    document.getElementById("job-skipped").textContent = skipped;
  } else {
    skippedWrap.classList.add("hidden");
  }
  const warn = document.getElementById("job-filter-warning");
  if (job.status === "completed" && (job.found || 0) === 0 && processed > 0) {
    warn.textContent =
      `Обработано ${processed} организаций, в выгрузку не попало ни одной (пропущено фильтром: ${skipped}). Ослабьте фильтры или увеличьте количество.`;
    warn.classList.remove("hidden");
  } else {
    warn.classList.add("hidden");
    warn.textContent = "";
  }
  document.getElementById("job-progress-text").textContent = `${job.progress || 0}%`;
  document.getElementById("job-progress-bar").style.width = `${job.progress || 0}%`;
  document.getElementById("job-log").textContent = (job.logs || []).join("\n");

  renderResults(job.results || [], job.status === "completed");

  if (job.status === "completed" || job.status === "failed") {
    clearInterval(pollTimer);
    pollTimer = null;
    const cleaned = job.files_cleaned;
    const cleanedNote = document.getElementById("files-cleaned-note");
    if (cleaned) {
      cleanedNote.classList.remove("hidden");
      hideDownloads();
    } else if (job.status === "completed") {
      cleanedNote.classList.add("hidden");
      const links = [
        ["download-excel", job.excel_path, `/api/jobs/${currentJobId}/excel`],
        ["download-json", job.json_path, `/api/jobs/${currentJobId}/json`],
        ["download-prompt", job.prompt_path, `/api/jobs/${currentJobId}/prompt`],
        ["download-agent-prompt", job.agent_prompt_path, `/api/jobs/${currentJobId}/agent-prompt`],
        ["download-archive", job.output_dir, `/api/jobs/${currentJobId}/archive`],
      ];
      links.forEach(([id, ready, href]) => {
        const el = document.getElementById(id);
        if (ready) {
          el.href = href;
          el.classList.remove("hidden");
        }
      });
    }
  }
}

function hideDownloads() {
  ["download-excel", "download-json", "download-prompt", "download-agent-prompt", "download-archive"].forEach((id) => {
    document.getElementById(id).classList.add("hidden");
  });
}

function renderResults(rows, finalPass) {
  const q = document.getElementById("service-search").value.toLowerCase();
  const tbody = document.getElementById("results-body");
  tbody.innerHTML = "";

  rows.forEach((row) => {
    const services = (row.services || []).join(" ");
    if (q && !services.toLowerCase().includes(q) && !(row.name || "").toLowerCase().includes(q)) {
      return;
    }
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.name)}</td>
      <td>${escapeHtml(row.phone)}</td>
      <td>${escapeHtml(row.category)}</td>
      <td>${(row.services || []).slice(0, 5).map((s) => `<span class="tag">${escapeHtml(s)}</span>`).join("")}</td>
      <td>📷 ${row.photos_count || 0} · 💬 ${row.reviews_scraped || 0} · 📋 ${row.menu_count || 0}</td>
      <td>${row.link ? `<a href="${row.link}" target="_blank" rel="noopener">🗺</a>` : ""}</td>
    `;
    tbody.appendChild(tr);
  });

  if (finalPass && rows.length) {
    document.querySelector('.tab[data-tab="results"]').click();
  }
}

document.getElementById("service-search").addEventListener("input", async () => {
  if (!currentJobId) return;
  const res = await fetch(`/api/jobs/${currentJobId}`);
  if (res.ok) renderResults((await res.json()).results || [], false);
});

async function loadHistory() {
  const res = await fetch("/api/jobs");
  const items = await res.json();
  const box = document.getElementById("history-list");
  box.innerHTML = items.length
    ? items.map((j) => `
      <div class="history-item" data-id="${j.id}">
        <strong>${escapeHtml(j.query || `${j.category || ""} ${j.city || ""}`.trim())}</strong>
        <div>${j.status} · найдено ${j.found || 0} · ${new Date(j.created_at).toLocaleString("ru-RU")}</div>
      </div>`).join("")
    : "<p>История пуста</p>";

  box.querySelectorAll(".history-item").forEach((el) => {
    el.addEventListener("click", () => {
      currentJobId = el.dataset.id;
      document.querySelector('.tab[data-tab="results"]').click();
      startPolling();
    });
  });
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

loadHistory();
