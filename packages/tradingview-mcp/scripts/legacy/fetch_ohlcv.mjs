/**
 * Fetches OHLCV bars from the live TradingView chart via CDP.
 * Prints JSON array of {time, open, high, low, close, volume} to stdout.
 * Usage: node fetch_ohlcv.mjs [bar_count]
 */
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const WebSocket = require('C:/Users/pashi/Downloads/Trading-bots/tradingview-mcp/node_modules/ws/index.js');

const COUNT = parseInt(process.argv[2] || '200');

async function getPages() {
  const r = await fetch('http://localhost:9222/json');
  return r.json();
}

async function cdpEval(wsUrl, expression) {
  return new Promise((resolve) => {
    const ws = new WebSocket(wsUrl);
    const timer = setTimeout(() => { ws.close(); resolve(null); }, 6000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate',
        params: { expression, returnByValue: true, awaitPromise: false } }));
    });
    ws.on('message', (data) => {
      clearTimeout(timer);
      ws.close();
      try {
        const r = JSON.parse(data);
        resolve(r?.result?.result?.value ?? null);
      } catch { resolve(null); }
    });
    ws.on('error', () => { clearTimeout(timer); resolve(null); });
  });
}

try {
  const pages = await getPages();
  const tv = pages.find(p => p.type === 'page' && p.url.includes('tradingview.com'));
  if (!tv) { console.log(JSON.stringify({ error: 'TradingView not found' })); process.exit(0); }

  const js = `
  (function() {
    try {
      var bars = window.TradingViewApi._activeChartWidgetWV.value()
                  ._chartWidget.model().mainSeries().bars();
      if (!bars || typeof bars.lastIndex !== 'function') return JSON.stringify({error:'no bars'});
      var end   = bars.lastIndex();
      var start = Math.max(bars.firstIndex(), end - ${COUNT} + 1);
      var result = [];
      for (var i = start; i <= end; i++) {
        var b = bars.valueAt(i);
        if (!b) continue;
        result.push({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4], volume: b[5] || 0 });
      }
      // also grab symbol from title
      var title = document.title;
      var symMatch = title.match(/^([A-Z0-9]+) /);
      return JSON.stringify({ bars: result, symbol: symMatch ? symMatch[1] : 'BSX260514C74300' });
    } catch(e) { return JSON.stringify({error: String(e)}); }
  })()
  `;

  const raw = await cdpEval(tv.webSocketDebuggerUrl, js);
  if (raw) {
    // raw is already a JSON string returned from the JS
    console.log(raw);
  } else {
    console.log(JSON.stringify({ error: 'CDP eval returned null' }));
  }
} catch(e) {
  console.log(JSON.stringify({ error: String(e) }));
}
