import asyncio
import csv
import os
from playwright.async_api import async_playwright

TV_SESSIONID      = os.environ["TV_SESSIONID"]
TV_SESSIONID_SIGN = os.environ["TV_SESSIONID_SIGN"]
CHART_URL         = os.environ["TV_CHART_URL"]
OUTPUT_FILE       = "results/backtest_sonuclari.csv"

def load_symbols():
    symbols = []
    with open("symbols.txt") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line)
    return symbols

async def login(context):
    await context.add_cookies([
        {"name": "sessionid",      "value": TV_SESSIONID,      "domain": ".tradingview.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
        {"name": "sessionid_sign", "value": TV_SESSIONID_SIGN, "domain": ".tradingview.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"}
    ])
    print("Cookie eklendi ✅")

async def change_symbol(page, symbol):
    search_term = symbol.split(":")[-1]
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
        await page.click('[id="header-toolbar-symbol-search"]', timeout=8000)
        await asyncio.sleep(0.5)
        await page.keyboard.press("Control+A")
        await page.keyboard.type(search_term, delay=40)
        await asyncio.sleep(1.5)
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)
        print(f"  Sembol: {search_term}")
    except Exception as e:
        print(f"  Sembol hatası: {e}")

async def wait_for_report(page, label=""):
    for selector in ['text="Key stats"', 'text="Total PnL"', 'text="Karlı işlemler"']:
        try:
            await page.wait_for_selector(selector, timeout=20000)
            print(f"  Rapor yüklendi ✅ {label}")
            return True
        except:
            continue
    print(f"  ⚠️ Rapor yüklenemedi {label}")
    return False

async def set_all_history(page):
    """
    activeArea class'lı tarih elementini bul, tıkla, Tüm geçmiş seç.
    """
    btn_info = await page.evaluate(
        """() => {
            const els = document.querySelectorAll('[class*="activeArea"]');
            for (const el of els) {
                const t = el.innerText || '';
                if (t.includes('\u2014') && /\d{4}/.test(t) && t.length < 80) {
                    const r = el.getBoundingClientRect();
                    return {
                        x: Math.round(r.left + r.width / 2),
                        y: Math.round(r.top + r.height / 2),
                        text: t.trim().slice(0, 50),
                        tag: el.tagName
                    };
                }
            }
            return null;
        }"""
    )

    if not btn_info:
        print("  ⚠️ Tarih butonu bulunamadı")
        return

    print(f"  Tarih: '{btn_info['text']}' @ ({btn_info['x']},{btn_info['y']})")
    await page.mouse.click(btn_info['x'], btn_info['y'])
    await asyncio.sleep(2)

    # Dropdown'dan Tüm geçmiş seç
    targets = ['Tüm geçmiş', 'Tüm Geçmiş', 'All history', 'All History']
    for target in targets:
        try:
            item = page.get_by_text(target, exact=True)
            if await item.count() > 0:
                await item.first.click(timeout=3000)
                await asyncio.sleep(2)
                print(f'  "{target}" seçildi ✅')
                return
        except:
            continue

    # Görünür li elementleri
    found_texts = []
    try:
        lis = page.locator('li')
        n = await lis.count()
        for idx in range(n):
            li = lis.nth(idx)
            try:
                t = (await li.inner_text(timeout=300)).strip()
                if t and len(t) < 40:
                    found_texts.append(t)
                if t in targets:
                    await li.click(timeout=2000)
                    await asyncio.sleep(2)
                    print(f'  "{t}" seçildi ✅')
                    return
            except:
                continue
    except:
        pass

    print(f"  ⚠️ Dropdown açılmadı. li'ler: {found_texts[:8]}")
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)

async def get_report_values(page):
    result = await page.evaluate(
        """() => {
            const res = {net_profit: 'N/A', max_drawdown: 'N/A', win_rate: 'N/A', trades: 'N/A'};
            let panel = null;
            for (const sel of ['[class*="backtesting"]', '[class*="strategyReport"]', '[class*="report"]']) {
                const el = document.querySelector(sel);
                if (el && el.innerText && el.innerText.length > 100) { panel = el; break; }
            }
            if (!panel) panel = document.body;
            const lines = panel.innerText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (res.net_profit === 'N/A' && (line.includes('Total PnL') || line.includes('Toplam K'))) {
                    for (let o = 1; o <= 5; o++) {
                        if (i+o >= lines.length) break;
                        const v = lines[i+o];
                        if (v.includes('%')) {
                            for (const p of v.split(/\s+/)) {
                                if (p.includes('%')) { res.net_profit = p.replace('%','').replace(',','.').replace('\u2212','-'); break; }
                            }
                            break;
                        }
                    }
                }
                if (res.max_drawdown === 'N/A' && (line.includes('Max drawdown') || line.includes('Maksimum'))) {
                    for (let o = 1; o <= 5; o++) {
                        if (i+o >= lines.length) break;
                        const v = lines[i+o];
                        if (v.includes('%')) {
                            for (const p of v.split(/\s+/)) {
                                if (p.includes('%')) { res.max_drawdown = p.replace('%','').replace(',','.').replace('\u2212','-'); break; }
                            }
                            break;
                        }
                    }
                }
                if ((res.win_rate === 'N/A' || res.trades === 'N/A') && line.includes('Karl\u0131 i\u015flemler')) {
                    for (let o = 1; o <= 6; o++) {
                        if (i+o >= lines.length) break;
                        const v = lines[i+o];
                        if (v.includes('%') && res.win_rate === 'N/A') {
                            for (const p of v.split(/\s+/)) {
                                if (p.includes('%')) { res.win_rate = p.replace('%','').replace(',','.'); break; }
                            }
                        }
                        if (v.includes('/') && res.trades === 'N/A') {
                            for (const p of v.split(/\s+/)) {
                                if (p.includes('/')) {
                                    const total = p.split('/').pop();
                                    if (/^\d+$/.test(total)) { res.trades = total; break; }
                                }
                            }
                        }
                        if (res.win_rate !== 'N/A' && res.trades !== 'N/A') break;
                    }
                }
            }
            return res;
        }"""
    )
    return result

def save_csv(data):
    if not data:
        return
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

async def main():
    os.makedirs("results", exist_ok=True)
    symbols = load_symbols()
    print(f"Toplam {len(symbols)} sembol")
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        await login(context)
        page = await context.new_page()

        print("Chart açılıyor...")
        await page.goto(CHART_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(15)
        await page.screenshot(path="results/chart_screen.png")
        print("Chart açıldı")

        try:
            await page.click('[data-name="backtesting"]', timeout=5000)
            await asyncio.sleep(3)
        except:
            print("Strategy Tester zaten açık")

        for i, symbol in enumerate(symbols):
            clean = symbol.replace("BINANCE:", "").replace("OKX:", "").replace(".P", "")
            print(f"\n[{i+1}/{len(symbols)}] {clean}")
            try:
                await change_symbol(page, symbol)
                loaded = await wait_for_report(page, "(ilk yükleme)")

                if loaded:
                    await set_all_history(page)
                    await asyncio.sleep(3)
                    await wait_for_report(page, "(tüm geçmiş)")

                if i == 0:
                    await page.screenshot(path="results/backtest_data.png")

                res = await get_report_values(page)
                all_results.append({
                    "Sembol":         clean,
                    "Net Kar %":      res["net_profit"],
                    "Max Drawdown %": res["max_drawdown"],
                    "Win Rate %":     res["win_rate"],
                    "İşlem Sayısı":   res["trades"],
                })
                print(f"  ✅ Kar:{res['net_profit']} | DD:{res['max_drawdown']} | Win:{res['win_rate']} | İşlem:{res['trades']}")

            except Exception as e:
                print(f"  ❌ {e}")
                all_results.append({
                    "Sembol": clean,
                    "Net Kar %": "HATA", "Max Drawdown %": "HATA",
                    "Win Rate %": "HATA", "İşlem Sayısı": "HATA",
                })

            if (i + 1) % 20 == 0:
                save_csv(all_results)
                print(f"  💾 Ara kayıt: {i+1} sembol")

        await browser.close()

    save_csv(all_results)
    print(f"\nTamamlandı → {OUTPUT_FILE}")

asyncio.run(main())
