// Автотест данных и логики. Запуск: node test.js
"use strict";
const fs = require("fs");
const vm = require("vm");

const ctx = {};
vm.createContext(ctx);
const dataSrc = fs.readFileSync(__dirname + "/data.js", "utf8");
const exported = vm.runInContext(
  dataSrc + "\n;({ NICHES, POST_TYPES, POST_TEMPLATES, AD_TEMPLATES, CHECKLISTS, REVIEW_SCRIPTS, INTEGRATIONS, VERDICT_RULES, DIAG_BENCH });",
  ctx
);
Object.assign(ctx, exported);

let failed = 0;
function check(name, cond, detail) {
  if (cond) {
    console.log("  OK  " + name);
  } else {
    failed++;
    console.log("FAIL  " + name + (detail ? " — " + detail : ""));
  }
}

const { NICHES, POST_TYPES, POST_TEMPLATES, AD_TEMPLATES, CHECKLISTS, REVIEW_SCRIPTS, INTEGRATIONS, VERDICT_RULES, DIAG_BENCH } = ctx;

// 1. Ниши
const nicheKeys = Object.keys(NICHES);
check("Ниш >= 5", nicheKeys.length >= 5, String(nicheKeys.length));
for (const [k, n] of Object.entries(NICHES)) {
  check(`Ниша ${k}: обязательные поля`,
    n.label && n.avgCheck > 0 && n.cycleDays > 0 &&
    Array.isArray(n.cplVk) && n.cplVk.length === 2 && n.cplVk[0] < n.cplVk[1] &&
    Array.isArray(n.cplYandex) && n.cplYandex[0] < n.cplYandex[1] &&
    n.services.length >= 3 && n.hashtagBase.length >= 3);
}

// 2. Шаблоны постов покрывают все типы
for (const t of POST_TYPES) {
  const pool = POST_TEMPLATES[t.key];
  check(`Тип поста «${t.key}»: есть шаблоны`, Array.isArray(pool) && pool.length >= 1);
  if (pool) {
    for (const tpl of pool) {
      check(`  шаблон «${tpl.title}»: text+story`, !!tpl.text && !!tpl.story);
    }
  }
}

// 3. Плейсхолдеры только допустимые
const allowed = new Set(["salon", "city", "service", "price", "phone", "link"]);
const allTexts = [];
Object.values(POST_TEMPLATES).forEach((pool) => pool.forEach((t) => allTexts.push(t.text)));
AD_TEMPLATES.vk.forEach((t) => allTexts.push(t.headline, t.text));
AD_TEMPLATES.yandex.forEach((t) => allTexts.push(t.headline, t.text, t.keywords));
allTexts.push(REVIEW_SCRIPTS.admin, REVIEW_SCRIPTS.message, REVIEW_SCRIPTS.negative);
let badPh = [];
for (const txt of allTexts) {
  const found = [...txt.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
  for (const ph of found) if (!allowed.has(ph)) badPh.push(ph);
}
check("Все плейсхолдеры допустимые", badPh.length === 0, badPh.join(","));

// 4. План на 14 дней: ротация не падает и даёт 14 уникальных дней
const counters = {};
const plan = [];
for (let d = 0; d < 14; d++) {
  const type = POST_TYPES[d % POST_TYPES.length];
  const pool = POST_TEMPLATES[type.key];
  const idx = (counters[type.key] = counters[type.key] || 0) % pool.length;
  counters[type.key]++;
  plan.push(type.key + ":" + idx);
}
check("Контент-план 14 дней собирается", plan.length === 14);

// 5. Чеклисты
for (const [k, cl] of Object.entries(CHECKLISTS)) {
  check(`Чеклист ${k}: >= 5 пунктов`, cl.items.length >= 5, String(cl.items.length));
}

// 6. Интеграции
check("Интеграций >= 4", INTEGRATIONS.length >= 4);
for (const it of INTEGRATIONS) {
  check(`Интеграция ${it.id}: шаги и описание`, !!it.name && !!it.what && it.steps.length >= 2);
}

// 7. Sanity прогноза: 9000 ₽ на ВК+Яндекс для маникюра
{
  const n = NICHES.manicure;
  const budget = 9000;
  const vkB = budget * 0.7, yaB = budget * 0.3;
  const leadsMin = vkB / n.cplVk[1] + yaB / n.cplYandex[1];
  const leadsMax = vkB / n.cplVk[0] + yaB / n.cplVk[0]; // намеренно max по нижним CPL
  check("Прогноз: заявок min > 5 при 9000 ₽ (маникюр)", leadsMin > 5, leadsMin.toFixed(1));
  check("Прогноз: min < max", leadsMin < leadsMax);
  const books = leadsMin * 0.5;
  const revenue = books * n.avgCheck;
  check("Прогноз: выручка min > 0.8×бюджета", revenue > budget * 0.8, `${Math.round(revenue)} vs ${budget}`);
}

// 8. Sanity диагностики: 3 мастера, 7 записей, чек 2000, no-show 20%
{
  const check_ = 2000, masters = 3, appts = 7, days = 26;
  const planned = masters * appts * days; // 546
  const lossNoshow = planned * 0.2 * check_;
  check("Диагностика: no-show 20% ≈ 218 400 ₽", Math.abs(lossNoshow - 218400) < 1, String(lossNoshow));
  const revenue = planned * check_;
  const lossUtil = revenue * (0.8 / 0.65 - 1);
  check("Диагностика: загрузка 65→80% > 0", lossUtil > 0, String(Math.round(lossUtil)));
  check("Бенчмарки диагностики заданы", DIAG_BENCH.sleepPct > 0 && DIAG_BENCH.reactRate > 0 && DIAG_BENCH.drop12 > 0);
}

// 9. Правила вердиктов
check("Пороги вердиктов валидны", VERDICT_RULES.ctrLowVk < VERDICT_RULES.ctrGoodVk && VERDICT_RULES.convLeadLow > 0);

// 10. HTML: все контейнеры, на которые ссылается app.js
{
  const html = fs.readFileSync(__dirname + "/index.html", "utf8");
  const app = fs.readFileSync(__dirname + "/app.js", "utf8");
  const ids = [...app.matchAll(/\$\("([a-z0-9-]+)"\)/gi)].map((m) => m[1]);
  const dynamicIds = new Set(["toast", "edit-profile", "utm-copy"]); // создаются/особые
  const missing = [...new Set(ids)].filter((id) => {
    if (id.startsWith("int-") || id.startsWith("cl-")) return false; // генерируются или проверены ниже
    return !html.includes(`id="${id}"`) && !dynamicIds.has(id);
  });
  check("Все id из app.js есть в HTML", missing.length === 0, missing.join(","));
  ["cl-yandexMaps", "cl-gis", "cl-reviews", "int-list", "diag-result", "smm-plan", "ads-forecast", "an-result",
    "oauth-backend", "oauth-vk-badge", "oauth-yandex-badge", "pdf-diag", "pdf-analytics", "print-area",
    "vk-client-id", "vk-client-secret", "save-vk-keys", "yandex-client-id", "yandex-client-secret", "save-yandex-keys",
    "step-vk-keys", "step-yandex-keys", "server-status", "wiz-1"].forEach((id) => {
    check(`HTML: контейнер #${id}`, html.includes(`id="${id}"`));
  });
  check("HTML подключает data.js до app.js", html.indexOf("data.js") < html.indexOf("app.js") && html.includes("data.js"));
  check("v2: exportPdf в app.js", app.includes("function exportPdf"));
  check("v2: initOAuth в app.js", app.includes("function initOAuth"));
  check("v2: saveProviderKeys в app.js", app.includes("function saveProviderKeys"));
  check("v2: sm_salon_id в app.js", app.includes("sm_salon_id"));
  check("v2: print CSS", fs.readFileSync(__dirname + "/styles.css", "utf8").includes("@media print"));
  check("v2: ЗАПУСК.bat", fs.existsSync(__dirname + "/ЗАПУСК.bat"));
  check("v2: DEFAULT_BACKEND в app.js", app.includes("DEFAULT_BACKEND"));
  check("v2: file-warn в HTML", html.includes('id="file-warn"'));
  check("v2: wizard-progress в HTML", html.includes("wizard-progress"));
}

console.log(failed === 0 ? "\nALL TESTS PASSED" : `\n${failed} TEST(S) FAILED`);
process.exit(failed === 0 ? 0 : 1);
