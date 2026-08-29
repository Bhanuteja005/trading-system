/**
 * Fetches current price from TradingView via CDP and prints JSON to stdout.
 * Called by server.py as a subprocess.
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
    const timer = setTimeout(() => { ws.close(); resolve(null); }, 4000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate',
        params: { expression, returnByValue: true } }));
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
  if (!tv) { console.log(JSON.stringify({ price: null, symbol: null, error: 'TradingView tab not found' })); process.exit(0); }

  // Get price from page title (most reliable — TradingView always shows it there)
  const title = await cdpEval(tv.webSocketDebuggerUrl, 'document.title');
  let price = null, symbol = null;
  if (title) {
    const m = title.match(/^([A-Z0-9]+)\s+([\d,]+\.?\d*)/);
    if (m) { symbol = m[1]; price = parseFloat(m[2].replace(/,/g, '')); }
  }

  // Fallback: try DOM element
  if (!price) {
    const raw = await cdpEval(tv.webSocketDebuggerUrl,
      `document.querySelector('[data-field="last_price"]')?.textContent?.trim() || ''`);
    if (raw) price = parseFloat(raw.replace(/,/g, ''));
  }

  console.log(JSON.stringify({ price, symbol: symbol || 'BSX260514C74300' }));
} catch(e) {
  console.log(JSON.stringify({ price: null, symbol: null, error: String(e) }));
}
