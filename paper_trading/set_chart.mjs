/**
 * Sets TradingView chart to 5-minute timeframe via CDP.
 */
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const WebSocket = require('C:/Users/pashi/Downloads/Trading-bots/tradingview-mcp/node_modules/ws/index.js');

async function getPages() {
  const r = await fetch('http://localhost:9222/json');
  return r.json();
}

async function cdpEval(wsUrl, expression) {
  return new Promise((resolve) => {
    const ws = new WebSocket(wsUrl);
    const timer = setTimeout(() => { ws.close(); resolve(null); }, 5000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate',
        params: { expression, returnByValue: true } }));
    });
    ws.on('message', (data) => {
      clearTimeout(timer);
      ws.close();
      try { resolve(JSON.parse(data)?.result?.result?.value ?? null); }
      catch { resolve(null); }
    });
    ws.on('error', () => { clearTimeout(timer); resolve(null); });
  });
}

const pages = await getPages();
const tv = pages.find(p => p.type === 'page' && p.url.includes('tradingview.com'));
if (!tv) { console.log('TradingView not found'); process.exit(1); }

// Set timeframe to 5 minutes using TradingView internal API
const js = `
(function() {
  try {
    var api = window.TradingViewApi._activeChartWidgetWV.value();
    api.setResolution('5');
    return 'timeframe set to 5m';
  } catch(e) {
    // fallback: click the 5m button in the toolbar
    var btns = document.querySelectorAll('[data-value="5"], [data-id="5"]');
    for (var b of btns) {
      if (b.textContent.trim() === '5') { b.click(); return 'clicked 5m button'; }
    }
    return 'error: ' + String(e);
  }
})()
`;

const result = await cdpEval(tv.webSocketDebuggerUrl, js);
console.log('Result:', result);

// Wait and get current bar count + latest price
await new Promise(r => setTimeout(r, 2000));
const check = await cdpEval(tv.webSocketDebuggerUrl, `
(function() {
  var title = document.title;
  var bars = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().mainSeries().bars();
  var last = bars.valueAt(bars.lastIndex());
  return JSON.stringify({ title: title.split(' ').slice(0,2).join(' '), lastClose: last ? last[4] : null });
})()
`);
console.log('Chart state:', check);
