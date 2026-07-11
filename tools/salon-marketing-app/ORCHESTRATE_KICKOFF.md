# Orchestrate — Салон-Маркетолог (parser-kart)

## Цель облачного planner

Построить self-service веб-приложение для владельцев салонов красоты на базе `parser-kart`: модули SMM-контент, таргет ВК/Яндекс, локальное продвижение Карты/2ГИС, performance-аналитика, диагностика потерь, мастера интеграций.

## Базовая линия (v1 уже есть локально)

```
parser-kart/tools/salon-marketing-app/
  index.html, app.js, data.js, styles.css, test.js (54 теста)
parser-kart/tools/salon-loss-calculator/
  index.html, TZ.md
```

Облачные агенты должны **расширять v1**, не переписывать с нуля.

## Потоки для параллельных воркеров

| Поток | Зона | Deliverables |
|-------|------|--------------|
| A | Frontend + UX | Онбординг, вкладки, PDF-экспорт, embed на лендинг parser-kart |
| B | Интеграции v2 | OAuth-мастера VK Ads, Яндекс.Директ, YML-прайс Яндекс.Бизнес, YClients CSV |
| C | Backend API | Минимальный сервер (FastAPI/Node) для OAuth callback и хранения токенов |
| D | Тесты + CI | Расширить test.js, e2e smoke, документация деплоя |

## Kickoff (после push на GitHub)

```powershell
cd "C:\Users\flkhg\.cursor\plugins\cache\cursor-public\orchestrate\a8145426e541afa424a403e3866496216c1b8142\skills\orchestrate\scripts"

bun cli.ts kickoff "Построить self-service веб-приложение Салон-Маркетолог для владельцев салонов красоты на базе parser-kart. v1 уже в tools/salon-marketing-app (6 модулей, 6 ниш, 54 теста). Расширить: OAuth интеграции VK Ads и Яндекс, бэкенд для токенов, PDF-отчёт, импорт CSV YClients, деплой. Не переписывать v1 — итерировать. Merge only if green: node test.js проходит." --repo https://github.com/vadimvasilisa3-dotcom/parser-kart --ref main
```

Ответ JSON → поле `url` → открыть в браузере.

## Предусловия

| Параметр | Статус |
|----------|--------|
| CURSOR_API_KEY | ✅ в среде Windows |
| bun + orchestrate scripts | ✅ `bun install` выполнен |
| GitHub repo parser-kart | ⏳ создать + push |
| Плагин Orchestrate | `/add-plugin orchestrate` в Cursor |

## Создание repo (один раз)

1. https://github.com/new → `parser-kart` (private)
2. Локально:

```powershell
cd c:\Projects\parser-kart
git init
git add .
git commit -m "feat: salon-marketing-app v1 + loss calculator"
git branch -M main
git remote add origin https://github.com/vadimvasilisa3-dotcom/parser-kart.git
git push -u origin main
```

3. Запустить kickoff (команда выше).

## Мониторинг после kickoff

```powershell
bun cli.ts status
bun cli.ts crawl <repo-path> <branch> <root-slug>
```

## Приёмка после мержа

```powershell
cd c:\Projects\parser-kart\tools\salon-marketing-app
node test.js
```
