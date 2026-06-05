import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const WS = require('C:/Users/pashi/Downloads/Trading-bots/tradingview-mcp/node_modules/ws/index.js');

async function cdpEval(wsUrl, expr) {
  return new Promise(r => {
    const ws = new WS(wsUrl);
    const t = setTimeout(() => { ws.close(); r(null); }, 6000);
    ws.on('open', () => ws.send(JSON.stringify({ id:1, method:'Runtime.evaluate', params:{ expression: expr, returnByValue:true } })));
    ws.on('message', d => { clearTimeout(t); ws.close(); try { r(JSON.parse(d)?.result?.result?.value); } catch { r(null); } });
    ws.on('error', () => { clearTimeout(t); r(null); });
  });
}

const pages = await (await fetch('http://localhost:9222/json')).json();
const tv = pages.find(p => p.type === 'page' && p.url.includes('tradingview.com'));
if (!tv) { console.log('not found'); process.exit(1); }

const r1 = await cdpEval(tv.webSocketDebuggerUrl,
  `(function(){ try{ window.TradingViewApi._activeChartWidgetWV.value().setResolution('1'); return 'ok'; }catch(e){ return String(e); } })()`);
console.error('Set 1-min:', r1);

await new Promise(r => setTimeout(r, 3000));

const check = await cdpEval(tv.webSocketDebuggerUrl,
  `(function(){ var t=document.title; var b=window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().mainSeries().bars(); var last=b.valueAt(b.lastIndex()); return JSON.stringify({title:t.split(' ').slice(0,2).join(' '), close: last?last[4]:null}); })()`);
console.log(check);
