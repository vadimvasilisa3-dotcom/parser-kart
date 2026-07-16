"use strict";

// ═══ Утилиты ═══════════════════════════════════════════════════
const $ = (id) => document.getElementById(id);
const LS = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(key);
      return v ? JSON.parse(v) : fallback;
    } catch (e) { return fallback; }
  },
  set(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* приватный режим */ }
  },
};

function fmt(n) {
  if (!Number.isFinite(n)) return "—";
  return Math.round(n).toLocaleString("ru-RU") + " ₽";
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

let toastTimer = null;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
}

function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => toast("Скопировано ✔"), () => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}
function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); toast("Скопировано ✔"); } catch (e) { toast("Не удалось скопировать"); }
  document.body.removeChild(ta);
}

// ═══ Профиль ═══════════════════════════════════════════════════
const DEFAULT_PROFILE = {
  niche: "manicure", salon: "", city: "", check: 0, budget: 9000, phone: "",
};

let profile = LS.get("salonApp.profile", null);

function nicheData() {
  return NICHES[profile?.niche] || NICHES.manicure;
}

function fill(template, extra = {}) {
  const n = nicheData();
  const map = {
    salon: profile?.salon || "нашем салоне",
    city: profile?.city || "вашем городе",
    service: extra.service || n.services[0],
    price: (extra.price || profile?.check || n.avgCheck).toLocaleString("ru-RU"),
    phone: profile?.phone || "телефону салона",
    link: extra.link || "(ссылка на отзыв)",
  };
  return template.replace(/\{(\w+)\}/g, (m, key) => (key in map ? map[key] : m));
}

function initOnboarding() {
  const sel = $("p-niche");
  sel.innerHTML = Object.entries(NICHES)
    .map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`)
    .join("");

  if (profile) {
    $("p-niche").value = profile.niche;
    $("p-salon").value = profile.salon;
    $("p-city").value = profile.city;
    $("p-check").value = profile.check || "";
    $("p-budget").value = profile.budget;
    $("p-phone").value = profile.phone;
  }

  $("p-niche").addEventListener("change", () => {
    const n = NICHES[$("p-niche").value];
    if (n && !$("p-check").value) $("p-check").placeholder = `Средний по нише: ${n.avgCheck}`;
  });

  $("p-save").addEventListener("click", () => {
    const niche = $("p-niche").value;
    const salon = $("p-salon").value.trim();
    const city = $("p-city").value.trim();
    if (!salon) {
      toast("Введите название салона или мастера");
      $("p-salon").focus();
      return;
    }
    if (!city) {
      toast("Укажите город — тексты будут с вашим городом");
      $("p-city").focus();
      return;
    }
    profile = {
      niche,
      salon,
      city,
      check: parseInt($("p-check").value, 10) || NICHES[niche].avgCheck,
      budget: parseInt($("p-budget").value, 10) || 0,
      phone: $("p-phone").value.trim(),
    };
    LS.set("salonApp.profile", profile);
    renderProfileBar();
    refreshAfterProfile();
    showFirstTip();
    toast("Готово! Смотрите вкладку «Диагностика»");
  });

  $("first-tip-close")?.addEventListener("click", () => {
    LS.set("salonApp.tipSeen", true);
    const tip = $("first-tip");
    if (tip) tip.hidden = true;
  });
}

function showFirstTip() {
  if (LS.get("salonApp.tipSeen", false)) return;
  const tip = $("first-tip");
  if (tip) tip.hidden = false;
}

function renderProfileBar() {
  if (!profile) return;
  const n = nicheData();
  $("onboarding").style.display = "none";
  $("tabs").style.display = "flex";
  const bar = $("profile-bar");
  bar.style.display = "block";
  bar.innerHTML = `
    <div style="margin-bottom:4px">
      <span class="profile-pill">${esc(n.label)}</span>
      <span class="profile-pill">${esc(profile.salon || "Салон")}</span>
      <span class="profile-pill">${esc(profile.city || "Город не указан")}</span>
      <span class="profile-pill">чек ${fmt(profile.check)}</span>
      <span class="profile-pill">бюджет ${fmt(profile.budget)}/мес</span>
      <button class="ghost" id="edit-profile" style="margin-left:4px">Изменить</button>
    </div>`;
  $("edit-profile").addEventListener("click", () => {
    $("onboarding").style.display = "block";
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

// ═══ Вкладки ═══════════════════════════════════════════════════
function initTabs() {
  document.querySelectorAll("nav.tabs button").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}
function switchTab(tab) {
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
}

// ═══ Диагностика ═══════════════════════════════════════════════
function calcDiag() {
  if (!profile) return;
  const masters = parseFloat($("d-masters").value) || 0;
  const appts = parseFloat($("d-appts").value) || 0;
  const noshow10 = parseFloat($("d-noshow").value) || 0;
  const util = (parseFloat($("d-util").value) || 0) / 100;
  const base = parseFloat($("d-base").value) || 0;
  const missedWeek = parseFloat($("d-missed").value) || 0;

  const check = profile.check || nicheData().avgCheck;
  const days = 26;
  const planned = masters * appts * days;
  const revenue = planned * check;
  const noshow = noshow10 / 10;

  const losses = [];

  const lossNoshow = planned * noshow * check;
  if (lossNoshow > 0) losses.push({
    name: "Неявки (no-show)",
    val: lossNoshow,
    fix: "Что делать: напоминание за 24 ч и за 2 ч (в CRM это галочка), предоплата 300–500 ₽ для новых. Цель — 1 из 20 вместо " + noshow10 + " из 10.",
    tab: null,
  });

  if (util > 0 && util < DIAG_BENCH.utilTarget / 100) {
    const lossUtil = revenue * (DIAG_BENCH.utilTarget / 100 / util - 1);
    losses.push({
      name: "Полупустое расписание (" + Math.round(util * 100) + "% вместо 80%)",
      val: lossUtil,
      fix: "Что делать: посты «свободные окна завтра» (вкладка SMM) + реклама на дневные слоты (вкладка Таргет).",
      tab: "smm",
    });
  }

  if (base > 0) {
    const lossSleep = base * DIAG_BENCH.sleepPct * DIAG_BENCH.reactRate * check;
    losses.push({
      name: "«Спящая» база — " + Math.round(base * DIAG_BENCH.sleepPct) + " человек вас забыли",
      val: lossSleep,
      fix: "Что делать: сообщение тем, кто не был " + nicheData().cycleDays + "+ дней (цикл вашей ниши). Возвращается 10–25% — бесплатные записи без рекламы.",
      tab: null,
    });
  }

  if (missedWeek > 0) {
    const lossMissed = missedWeek * 4.3 * 0.55 * check;
    losses.push({
      name: "Пропущенные звонки и сообщения",
      val: lossMissed,
      fix: "Что делать: онлайн-запись 24/7 (вкладка Интеграции → виджет записи) — клиент записывается сам, даже ночью.",
      tab: "integrations",
    });
  }

  losses.sort((a, b) => b.val - a.val);
  const total = losses.reduce((s, l) => s + l.val, 0) * 0.88;

  const rows = losses.map((l) => `
    <div class="loss-row">
      <div class="loss-name">${esc(l.name)}</div>
      <div class="loss-val">≈ ${fmt(l.val)}/мес</div>
      <div class="loss-fix">${esc(l.fix)}${l.tab ? ` <a data-goto="${l.tab}">Открыть раздел →</a>` : ""}</div>
    </div>`).join("");

  $("diag-result").innerHTML = `
    <div class="warn-box" style="margin-top:16px">
      <b>Оценка потерь: ≈ ${fmt(total)} в месяц</b> (${fmt(total * 12)} в год) при выручке ~${fmt(revenue)}.
      Это модель по отраслевым нормам — реальную цифру покажет ваша CRM. Но порядок величины обычно совпадает.
    </div>
    ${rows}
    <div class="explain" style="margin-top:14px"><b>С чего начать:</b> почините верхнюю строку списка — она самая дорогая. Обычно это 1–2 недели работы и 0 ₽ бюджета. Реклама — только после этого.</div>`;

  $("diag-result").querySelectorAll("[data-goto]").forEach((a) => {
    a.addEventListener("click", () => switchTab(a.dataset.goto));
  });
}

// ═══ SMM ════════════════════════════════════════════════════════
const VK_SETUP_CHECKLIST = [
  "Обложка: фото салона/работ + телефон + «Онлайн-запись» (не стоковая картинка)",
  "Название группы: «Салон | Услуга | Город» — так вас находят в поиске ВК",
  "Кнопка действия: «Записаться» → ссылка на онлайн-запись или сообщения",
  "Раздел «Услуги» заполнен с ценами (это витрина, работает без постов)",
  "Закреплённый пост: кто вы, адрес, 3 лучшие работы, как записаться",
  "Сообщения сообщества включены, отвечаете быстрее 15 минут в рабочее время",
  "Виджет «Отзывы» или подборка постов-отзывов",
  "Адрес и график в контактах совпадают с Яндекс.Картами",
];

function initSmm() {
  const n = nicheData();
  $("smm-service").innerHTML = n.services.map((s) => `<option>${esc(s)}</option>`).join("");
  $("smm-price").value = profile?.check || n.avgCheck;

  $("smm-checklist").innerHTML = renderChecklist("vkSetup", VK_SETUP_CHECKLIST);
  bindChecklist("vkSetup");

  // onclick вместо addEventListener: initSmm вызывается при каждом сохранении профиля
  $("smm-gen").onclick = generatePlan;
}

function generatePlan() {
  const service = $("smm-service").value;
  const price = parseInt($("smm-price").value, 10) || nicheData().avgCheck;
  const n = nicheData();
  const counters = {};
  const days = [];

  for (let d = 0; d < 14; d++) {
    const type = POST_TYPES[d % POST_TYPES.length];
    const pool = POST_TEMPLATES[type.key];
    const idx = (counters[type.key] = (counters[type.key] || 0)) % pool.length;
    counters[type.key]++;
    const tpl = pool[idx];
    const text = fill(tpl.text, { service, price });
    const hashtags = n.hashtagBase
      .map((h) => "#" + h + (profile.city ? profile.city.split(/[ ,]/)[0].toLowerCase() : ""))
      .slice(0, 3)
      .join(" ");
    days.push({ day: d + 1, type, tpl, text: text + "\n\n" + hashtags });
  }

  $("smm-plan").innerHTML = days.map((d) => `
    <div class="day-card">
      <div class="day-head">
        <span class="day-num">День ${d.day} — ${esc(d.tpl.title)}</span>
        <span class="badge">${esc(d.type.label)} · цель: ${esc(d.type.goal)}</span>
      </div>
      <div class="post-text">${esc(d.text)}</div>
      <button class="ghost copy-post" data-day="${d.day - 1}">📋 Копировать пост</button>
      <div class="story-hint" style="margin-top:6px">${esc(d.tpl.story)}</div>
    </div>`).join("");

  window.__plan = days;
  $("smm-plan").querySelectorAll(".copy-post").forEach((btn) => {
    btn.addEventListener("click", () => copyText(window.__plan[+btn.dataset.day].text));
  });
  toast("План на 14 дней готов");
}

// ═══ Таргет ═════════════════════════════════════════════════════
function initAds() {
  $("ads-budget").value = profile?.budget || 9000;
  $("ads-calc").addEventListener("click", calcForecast);
  renderAdTemplates();
  $("utm-gen").addEventListener("click", buildUtm);
  calcForecast();
}

function calcForecast() {
  const budget = parseFloat($("ads-budget").value) || 0;
  const split = $("ads-split").value;
  const n = nicheData();
  const check = profile.check || n.avgCheck;

  let parts = [];
  if (split === "vk") parts = [{ name: "ВК", share: 1, cpl: n.cplVk }];
  else if (split === "yandex") parts = [{ name: "Яндекс", share: 1, cpl: n.cplYandex }];
  else parts = [
    { name: "ВК", share: 0.7, cpl: n.cplVk },
    { name: "Яндекс", share: 0.3, cpl: n.cplYandex },
  ];

  let leadsMin = 0, leadsMax = 0;
  const rows = parts.map((p) => {
    const b = budget * p.share;
    const lMin = b / p.cpl[1];
    const lMax = b / p.cpl[0];
    leadsMin += lMin; leadsMax += lMax;
    return `<div class="metric"><div class="m-val">${Math.floor(lMin)}–${Math.floor(lMax)}</div><div class="m-label">${p.name}: заявок (${fmt(b)}, CPL ${p.cpl[0]}–${p.cpl[1]} ₽)</div></div>`;
  }).join("");

  const bookMin = Math.floor(leadsMin * 0.5);
  const bookMax = Math.floor(leadsMax * 0.7);
  const revMin = bookMin * check;
  const revMax = bookMax * check;
  const roiOk = revMin > budget;

  $("ads-forecast").innerHTML = `
    <div class="metric-grid">${rows}
      <div class="metric"><div class="m-val">${bookMin}–${bookMax}</div><div class="m-label">записей (50–70% заявок)</div></div>
      <div class="metric ${roiOk ? "good" : "bad"}"><div class="m-val">${fmt(revMin)}–${fmt(revMax)}</div><div class="m-label">выручка с первых визитов</div></div>
    </div>
    <div class="${roiOk ? "explain" : "warn-box"}">
      ${roiOk
        ? "<b>Прогноз положительный:</b> даже нижняя граница выручки перекрывает бюджет. И это без повторных визитов — постоянные клиенты умножат результат."
        : "<b>Осторожно:</b> при плохом раскладе первые визиты не окупят бюджет сразу. Это нормально для ниши — клиент окупается на повторных визитах (LTV). Но сначала почините неявки и перезапись (вкладка Диагностика), иначе реклама уйдёт в песок."}
      Дневной бюджет: ~${fmt(budget / 30)}/день. Первые выводы — не раньше 5–7 дней открутки.
    </div>`;
}

function renderAdTemplates() {
  const service = nicheData().services[0];
  const price = profile.check || nicheData().avgCheck;

  const vk = AD_TEMPLATES.vk.map((t, i) => {
    const head = fill(t.headline, { service, price });
    const text = fill(t.text, { service, price });
    return `
    <div class="day-card">
      <div class="day-head"><span class="day-num">ВК · ${esc(t.name)}</span><span class="badge">объявление</span></div>
      <div class="post-text"><b>${esc(head)}</b>\n\n${esc(text)}</div>
      <div class="story-hint">Аудитория: ${esc(t.audience)}</div>
      <button class="ghost copy-ad" data-txt="${esc(head)}\n\n${esc(text)}">📋 Копировать</button>
    </div>`;
  }).join("");

  const ya = AD_TEMPLATES.yandex.map((t) => {
    const head = fill(t.headline, { service, price });
    const text = fill(t.text, { service, price });
    const kw = fill(t.keywords, { service, price });
    return `
    <div class="day-card">
      <div class="day-head"><span class="day-num">Яндекс · ${esc(t.name)}</span><span class="badge">поиск</span></div>
      <div class="post-text"><b>${esc(head)}</b>\n${esc(text)}</div>
      <div class="story-hint">Ключевые слова: ${esc(kw)}</div>
      <button class="ghost copy-ad" data-txt="${esc(head)}\n${esc(text)}">📋 Копировать</button>
    </div>`;
  }).join("");

  $("ads-templates").innerHTML = vk + ya;
  $("ads-templates").querySelectorAll(".copy-ad").forEach((btn) => {
    btn.addEventListener("click", () => copyText(btn.dataset.txt));
  });
}

function buildUtm() {
  let url = ($("utm-url").value || "").trim();
  const source = $("utm-source").value;
  const campaign = ($("utm-campaign").value || "salon").trim().replace(/\s+/g, "_");
  if (!url) { toast("Вставьте ссылку"); return; }
  if (!/^https?:\/\//i.test(url)) url = "https://" + url;
  const sep = url.includes("?") ? "&" : "?";
  const result = `${url}${sep}utm_source=${encodeURIComponent(source)}&utm_medium=cpc&utm_campaign=${encodeURIComponent(campaign)}`;
  $("utm-result").innerHTML = `
    <div class="post-text" style="margin-top:10px">${esc(result)}</div>
    <button class="ghost" id="utm-copy">📋 Копировать ссылку</button>`;
  $("utm-copy").addEventListener("click", () => copyText(result));
}

// ═══ Локалка: чеклисты с прогрессом ═════════════════════════════
function renderChecklist(key, items) {
  const state = LS.get("salonApp.check." + key, {});
  const done = items.filter((_, i) => state[i]).length;
  const pctDone = items.length ? Math.round((done / items.length) * 100) : 0;
  const rows = items.map((item, i) => `
    <div class="check-item ${state[i] ? "done" : ""}">
      <input type="checkbox" data-key="${key}" data-idx="${i}" ${state[i] ? "checked" : ""}>
      <span>${esc(item)}</span>
    </div>`).join("");
  return `
    <div class="hint">Выполнено: ${done} из ${items.length}</div>
    <div class="progress-line"><div style="width:${pctDone}%"></div></div>
    ${rows}`;
}

function bindChecklist(key) {
  document.querySelectorAll(`input[type="checkbox"][data-key="${key}"]`).forEach((cb) => {
    cb.addEventListener("change", () => {
      const state = LS.get("salonApp.check." + key, {});
      state[cb.dataset.idx] = cb.checked;
      LS.set("salonApp.check." + key, state);
      // Перерисовать контейнер
      const containerMap = { yandexMaps: "cl-yandexMaps", gis: "cl-gis", reviews: "cl-reviews", vkSetup: "smm-checklist" };
      const containerId = containerMap[key];
      if (containerId) {
        const items = key === "vkSetup" ? VK_SETUP_CHECKLIST : CHECKLISTS[key].items;
        $(containerId).innerHTML = renderChecklist(key, items);
        bindChecklist(key);
      }
    });
  });
}

function initLocal() {
  ["yandexMaps", "gis", "reviews"].forEach((key) => {
    $("cl-" + key).innerHTML = renderChecklist(key, CHECKLISTS[key].items);
    bindChecklist(key);
  });

  $("review-scripts").innerHTML = [
    { label: "Админ при оплате", text: fill(REVIEW_SCRIPTS.admin) },
    { label: "Сообщение после визита", text: fill(REVIEW_SCRIPTS.message) },
    { label: "Ответ на негативный отзыв", text: fill(REVIEW_SCRIPTS.negative) },
  ].map((s, i) => `
    <div class="day-card">
      <div class="day-head"><span class="day-num">${esc(s.label)}</span></div>
      <div class="post-text">${esc(s.text)}</div>
      <button class="ghost copy-script" data-i="${i}" data-txt="${esc(s.text)}">📋 Копировать</button>
    </div>`).join("");
  $("review-scripts").querySelectorAll(".copy-script").forEach((btn) => {
    btn.addEventListener("click", () => copyText(btn.dataset.txt));
  });
}

// ═══ Аналитика ══════════════════════════════════════════════════
function initAnalytics() {
  $("an-calc").addEventListener("click", calcAnalytics);
}

function calcAnalytics() {
  if (!profile) { toast("Сначала заполните профиль салона"); return; }
  const spend = parseFloat($("an-spend").value) || 0;
  const imp = parseFloat($("an-imp").value) || 0;
  const clicks = parseFloat($("an-clicks").value) || 0;
  const leads = parseFloat($("an-leads").value) || 0;
  const books = parseFloat($("an-books").value) || 0;
  const visits = parseFloat($("an-visits").value) || 0;

  const n = nicheData();
  const check = profile.check || n.avgCheck;

  const ctr = imp > 0 ? (clicks / imp) * 100 : 0;
  const cpc = clicks > 0 ? spend / clicks : 0;
  const cpl = leads > 0 ? spend / leads : 0;
  const convLead = clicks > 0 ? (leads / clicks) * 100 : 0;
  const convBook = leads > 0 ? (books / leads) * 100 : 0;
  const showRate = books > 0 ? (visits / books) * 100 : 0;
  const cpVisit = visits > 0 ? spend / visits : 0;
  const revenue = visits * check;

  const verdicts = [];
  if (imp > 0 && ctr < VERDICT_RULES.ctrLowVk) {
    verdicts.push({ level: "warn", text: `CTR ${ctr.toFixed(2)}% — объявление не цепляет (норма ВК от ${VERDICT_RULES.ctrLowVk}%). Поменяйте картинку на «до/после» и добавьте цену в заголовок. Тексты — во вкладке «Таргет».` });
  } else if (imp > 0 && ctr >= VERDICT_RULES.ctrGoodVk) {
    verdicts.push({ level: "ok", text: `CTR ${ctr.toFixed(2)}% — креатив работает, не трогайте его. Можно аккуратно поднять бюджет на 20–30%.` });
  }
  if (clicks >= 30 && convLead < 5) {
    verdicts.push({ level: "warn", text: `Из ${Math.round(clicks)} кликов только ${Math.round(leads)} заявок (${convLead.toFixed(1)}%). Люди приходят и уходят: проверьте, куда ведёт ссылка — там должны быть цены, работы и кнопка записи на первом экране.` });
  }
  if (leads >= 5 && convBook < VERDICT_RULES.convLeadLow) {
    verdicts.push({ level: "warn", text: `Записывается лишь ${convBook.toFixed(0)}% написавших. Дыра в обработке: отвечать надо в первые 15 минут и сразу предлагать 2 варианта времени, а не спрашивать «когда вам удобно?».` });
  }
  if (books >= 3 && showRate < 100 - VERDICT_RULES.noshowHigh) {
    verdicts.push({ level: "warn", text: `Дошло ${showRate.toFixed(0)}% записавшихся — теряете оплаченные рекламой визиты. Включите напоминания за 24 ч и за 2 ч (вкладка Диагностика).` });
  }
  if (cpl > 0 && cpl > n.cplVk[1] * 1.5) {
    verdicts.push({ level: "warn", text: `Заявка стоит ${fmt(cpl)} — дорого для ниши «${n.label}» (норма ${n.cplVk[0]}–${n.cplVk[1]} ₽ в ВК). Сузьте гео до 3 км и поставьте цену в объявление — отсеет нецелевых.` });
  } else if (cpl > 0 && cpl <= n.cplVk[1]) {
    verdicts.push({ level: "ok", text: `Заявка за ${fmt(cpl)} — в норме ниши. Канал рабочий, масштабируйте постепенно.` });
  }
  if (revenue > spend && visits > 0) {
    verdicts.push({ level: "ok", text: `Выручка первых визитов ${fmt(revenue)} против ${fmt(spend)} расходов — реклама окупилась сразу. Каждый удержанный клиент добавит ещё ${fmt(check * 5)}+ в год.` });
  } else if (spend > 0 && visits > 0) {
    verdicts.push({ level: "warn", text: `Первые визиты (${fmt(revenue)}) пока не перекрыли расход (${fmt(spend)}). Не паникуйте: смотрите на повторные визиты. Но если через месяц картина та же — меняйте оффер.` });
  }
  if (!verdicts.length) verdicts.push({ level: "ok", text: "Мало данных для вердикта — докрутите рекламу до 30+ кликов и вернитесь." });

  $("an-result").innerHTML = `
    <div class="metric-grid" style="margin-top:16px">
      <div class="metric"><div class="m-val">${ctr.toFixed(2)}%</div><div class="m-label">CTR (клики/показы)</div></div>
      <div class="metric"><div class="m-val">${fmt(cpc)}</div><div class="m-label">Цена клика</div></div>
      <div class="metric"><div class="m-val">${fmt(cpl)}</div><div class="m-label">Цена заявки (CPL)</div></div>
      <div class="metric"><div class="m-val">${convBook.toFixed(0)}%</div><div class="m-label">Заявка → запись</div></div>
      <div class="metric"><div class="m-val">${showRate.toFixed(0)}%</div><div class="m-label">Доходимость</div></div>
      <div class="metric ${revenue >= spend ? "good" : "bad"}"><div class="m-val">${fmt(cpVisit)}</div><div class="m-label">Цена пришедшего клиента</div></div>
    </div>
    ${verdicts.map((v) => `<div class="${v.level === "ok" ? "explain" : "warn-box"}">${esc(v.text)}</div>`).join("")}`;
}

// ═══ Подключение рекламы (всё внутри приложения) ═════════════════
const CONNECT_LABELS = {
  vk: { name: "ВКонтакте", card: "card-vk", steps: [
    "Нажмите «Открыть окно входа» — появится маленькое окно.",
    "Войдите в свой аккаунт ВКонтакте (как обычно).",
    "Нажмите «Разрешить» — окно закроется, вы останетесь здесь.",
  ]},
  yandex: { name: "Яндекс.Директ", card: "card-yandex", steps: [
    "Нажмите «Открыть окно входа» — появится маленькое окно.",
    "Войдите в Яндекс под своим логином.",
    "Нажмите «Разрешить» — окно закроется, вы останетесь здесь.",
  ]},
};

const DEFAULT_BACKEND = "http://127.0.0.1:8000";
let connectProvider = null;
let oauthPopup = null;
let popupTimer = null;

function getSalonId() {
  let id = localStorage.getItem("sm_salon_id");
  if (!id) {
    id = "salon-" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("sm_salon_id", id);
  }
  return id;
}

function getBackendUrl() {
  const el = $("oauth-backend");
  return (el?.value || localStorage.getItem("sm_backend_url") || DEFAULT_BACKEND).trim().replace(/\/$/, "");
}

function setOAuthBadge(provider, connected) {
  const el = $(provider === "vk" ? "oauth-vk-badge" : "oauth-yandex-badge");
  const card = $(provider === "vk" ? "card-vk" : "card-yandex");
  if (el) {
    el.textContent = connected ? "✓ Подключено" : "не подключено";
    el.classList.toggle("on", !!connected);
  }
  if (card) card.classList.toggle("connected", !!connected);
}

async function backendOnline() {
  const base = getBackendUrl();
  try {
    const r = await fetch(`${base}/health`);
    return r.ok;
  } catch (e) {
    return false;
  }
}

async function refreshOAuthStatus(silent) {
  const base = getBackendUrl();
  localStorage.setItem("sm_backend_url", base);
  if (!(await backendOnline())) {
    if (!silent) toast("Запустите ЗАПУСК.bat");
    return;
  }
  try {
    const r = await fetch(`${base}/oauth/status?salon_id=${encodeURIComponent(getSalonId())}`);
    if (!r.ok) throw new Error(String(r.status));
    const data = await r.json();
    setOAuthBadge("vk", data.vk?.connected);
    setOAuthBadge("yandex", data.yandex?.connected);
    if (!silent) toast("Статус обновлён");
  } catch (e) {
    if (!silent) toast("Не удалось проверить подключение");
  }
}

function showConnectMsg(text) {
  const box = $("connect-modal-msg");
  if (!box) return;
  box.textContent = text;
  box.hidden = !text;
}

function closeConnectModal() {
  const m = $("connect-modal");
  if (m) m.hidden = true;
  connectProvider = null;
  if (oauthPopup && !oauthPopup.closed) oauthPopup.close();
  oauthPopup = null;
  clearInterval(popupTimer);
  popupTimer = null;
  showConnectMsg("");
  const kf = $("connect-key-form");
  if (kf) kf.hidden = true;
  const ki = $("connect-key-input");
  if (ki) ki.value = "";
}

function openConnectModal(provider) {
  connectProvider = provider;
  const info = CONNECT_LABELS[provider];
  const m = $("connect-modal");
  const body = $("connect-modal-body");
  const wait = $("connect-modal-wait");
  if (!m || !info) return;
  $("connect-modal-title").textContent = "Подключение: " + info.name;
  $("connect-steps").innerHTML = info.steps.map((s, i) =>
    `<div class="connect-step"><span class="connect-step-num">${i + 1}</span><span>${esc(s)}</span></div>`
  ).join("");
  if (body) body.hidden = false;
  if (wait) wait.hidden = true;
  showConnectMsg("");
  m.hidden = false;
}

async function startConnectPopup() {
  if (!connectProvider) return;
  const base = getBackendUrl();
  if (!(await backendOnline())) {
    showConnectMsg("Сначала запустите ЗАПУСК.bat на компьютере.");
    return;
  }
  try {
    const cfg = await fetch(`${base}/oauth/config`).then((r) => r.json());
    if (!cfg[connectProvider]?.ready) {
      showConnectMsg(
        "Автовход пока недоступен. Нажмите «У меня есть ключ доступа» и вставьте ключ — вы никуда не уйдёте. " +
        "Или пользуйтесь вкладками SMM и Таргет — там готовые тексты для рекламы."
      );
      return;
    }
  } catch (e) {
    showConnectMsg("Сервер не отвечает. Запустите ЗАПУСК.bat.");
    return;
  }
  const url = `${base}/oauth/${connectProvider}/start?salon_id=${encodeURIComponent(getSalonId())}`;
  const w = 520, h = 680;
  const left = Math.max(0, (screen.width - w) / 2);
  const top = Math.max(0, (screen.height - h) / 2);
  oauthPopup = window.open(
    url,
    "salon_oauth_" + connectProvider,
    `width=${w},height=${h},left=${left},top=${top},noopener`
  );
  if (!oauthPopup) {
    showConnectMsg("Браузер заблокировал окно. Разрешите всплывающие окна для этого сайта или используйте «Ключ доступа».");
    return;
  }
  $("connect-modal-body").hidden = true;
  $("connect-modal-wait").hidden = false;
  clearInterval(popupTimer);
  popupTimer = setInterval(() => {
    if (oauthPopup && oauthPopup.closed) {
      clearInterval(popupTimer);
      popupTimer = null;
      refreshOAuthStatus(true);
    }
  }, 500);
}

async function saveManualKey() {
  if (!connectProvider) return;
  const token = ($("connect-key-input")?.value || "").trim();
  if (token.length < 8) {
    showConnectMsg("Вставьте ключ целиком — он длиннее 8 символов.");
    return;
  }
  const base = getBackendUrl();
  if (!(await backendOnline())) {
    showConnectMsg("Запустите ЗАПУСК.bat");
    return;
  }
  try {
    const r = await fetch(
      `${base}/oauth/${connectProvider}/manual?salon_id=${encodeURIComponent(getSalonId())}`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) }
    );
    if (!r.ok) throw new Error(String(r.status));
    closeConnectModal();
    await refreshOAuthStatus(true);
    toast(CONNECT_LABELS[connectProvider].name + " подключён ✔");
  } catch (e) {
    showConnectMsg("Не удалось сохранить ключ. Проверьте, что ЗАПУСК.bat запущен.");
  }
}

function onOAuthMessage(e) {
  if (e.data?.type !== "salon-oauth") return;
  const provider = e.data.connected || (e.data.error || "").replace("keys_missing_", "");
  closeConnectModal();
  if (e.data.connected) {
    refreshOAuthStatus(true);
    toast(CONNECT_LABELS[e.data.connected]?.name + " подключён ✔");
  } else if (e.data.error) {
    if (String(e.data.error).includes("keys_missing")) {
      toast("Используйте «Ключ доступа» или вкладки SMM/Таргет");
    } else {
      toast("Не удалось подключить — попробуйте снова");
    }
    refreshOAuthStatus(true);
  }
}

async function disconnectOAuth(provider) {
  const base = getBackendUrl();
  if (!(await backendOnline())) return;
  try {
    await fetch(`${base}/oauth/${provider}/disconnect?salon_id=${encodeURIComponent(getSalonId())}`, { method: "POST" });
    toast("Отключено");
    refreshOAuthStatus(true);
  } catch (e) {
    toast("Ошибка отключения");
  }
}

function handleOAuthReturn() {
  const p = new URLSearchParams(location.search);
  const connected = p.get("connected");
  const err = p.get("oauth_error");
  if (!connected && !err) return;
  if (connected) {
    toast(CONNECT_LABELS[connected]?.name + " подключён ✔");
    history.replaceState({}, "", location.pathname);
    refreshOAuthStatus(true);
  } else if (err) {
    toast(err.includes("keys_missing") ? "Вставьте ключ доступа в приложении" : "Не удалось подключить");
    history.replaceState({}, "", location.pathname);
  }
}

function initOAuth() {
  localStorage.setItem("sm_backend_url", getBackendUrl());
  if (location.protocol === "file:") {
    const w = $("file-warn");
    if (w) w.style.display = "block";
  }
  window.addEventListener("message", onOAuthMessage);
  $("oauth-vk-connect")?.addEventListener("click", () => openConnectModal("vk"));
  $("oauth-yandex-connect")?.addEventListener("click", () => openConnectModal("yandex"));
  $("oauth-vk-disconnect")?.addEventListener("click", () => disconnectOAuth("vk"));
  $("oauth-yandex-disconnect")?.addEventListener("click", () => disconnectOAuth("yandex"));
  $("connect-modal-close")?.addEventListener("click", closeConnectModal);
  $("connect-modal-cancel")?.addEventListener("click", closeConnectModal);
  $("connect-modal-start")?.addEventListener("click", startConnectPopup);
  $("connect-modal-check")?.addEventListener("click", () => refreshOAuthStatus(false));
  $("connect-modal-key-toggle")?.addEventListener("click", () => {
    const kf = $("connect-key-form");
    if (kf) kf.hidden = !kf.hidden;
  });
  $("connect-key-save")?.addEventListener("click", saveManualKey);
  $("connect-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "connect-modal") closeConnectModal();
  });
  handleOAuthReturn();
  if (location.protocol !== "file:") refreshOAuthStatus(true);
}

// ═══ PDF export v2 ══════════════════════════════════════════════
function exportPdf(section) {
  if (!profile) { toast("Сначала сохраните профиль салона"); return; }
  const n = nicheData();
  const title = section === "diag" ? "Диагностика потерь" : "Аналитика недели";
  const body = section === "diag" ? ($("diag-result")?.innerHTML || "") : ($("an-result")?.innerHTML || "");
  const area = $("print-area");
  if (!area) { window.print(); return; }
  area.innerHTML = `
    <h1>Салон-Маркетолог — ${esc(title)}</h1>
    <p><b>${esc(profile?.salon || "Салон")}</b> · ${esc(n.label)} · ${esc(profile?.city || "")}</p>
    <p>Дата: ${new Date().toLocaleDateString("ru-RU")}</p>
    <hr>${body}`;
  window.print();
  area.innerHTML = "";
}

// ═══ Интеграции ═════════════════════════════════════════════════
function initIntegrations() {
  $("int-list").innerHTML = INTEGRATIONS.map((it) => `
    <div class="int-card" id="int-${it.id}">
      <div class="int-head">
        <h4>${esc(it.name)}</h4>
        <button class="ghost int-toggle" data-id="${it.id}">Как подключить</button>
      </div>
      <div class="int-what">${esc(it.what)}</div>
      <div class="int-what"><b>Автоматизация:</b> ${esc(it.auto)}</div>
      <div class="int-steps">
        <ol>${it.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
        ${it.link ? `<div style="margin-top:8px"><a href="${esc(it.link)}" target="_blank" rel="noopener">${esc(it.link)} ↗</a></div>` : ""}
      </div>
    </div>`).join("");

  $("int-list").querySelectorAll(".int-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = $("int-" + btn.dataset.id);
      card.classList.toggle("open");
      btn.textContent = card.classList.contains("open") ? "Свернуть" : "Как подключить";
    });
  });
}

// ═══ Запуск ═════════════════════════════════════════════════════
function refreshAfterProfile() {
  initSmm();
  initAdsRefresh();
  calcDiag();
}

let adsInited = false;
function initAdsRefresh() {
  if (!adsInited) {
    initAds();
    adsInited = true;
  } else {
    $("ads-budget").value = profile.budget || $("ads-budget").value;
    renderAdTemplates();
    calcForecast();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initOnboarding();
  initTabs();
  initLocal();
  initAnalytics();
  initOAuth();
  initIntegrations();
  $("pdf-diag")?.addEventListener("click", () => exportPdf("diag"));
  $("pdf-analytics")?.addEventListener("click", () => exportPdf("analytics"));

  ["d-masters", "d-appts", "d-noshow", "d-util", "d-base", "d-missed"].forEach((id) => {
    $(id).addEventListener("input", calcDiag);
  });

  if (profile) {
    renderProfileBar();
    refreshAfterProfile();
    showFirstTip();
  }
});
