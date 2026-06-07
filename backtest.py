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

async def close_any_dropdown(page):
    """Açık dropdown varsa Escape ile kapat."""
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
    except:
        pass

async def change_symbol(page, symbol):
    search_term = symbol.split(":")[-1]
    # Önce açık dropdown varsa kapat
    await close_any_dropdown(page)
    try:
        await page.click('[id="header-toolbar-symbol-search"]', timeout=8000)
        await asyncio.sleep(0.5)
        await page.keyboard.press("Control+A")
        await page.keyboard.type(search_term, delay=40)
        await asyncio.sleep(1.5)
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)
        print(f"  Sembol değiştirildi: {search_term}")
    except Exception as e:
        print(f"  Sembol hatası: {e}")

async def wait_for_report(page, label=""):
    """Strateji raporunun yüklenmesini bekle."""
    # "Key stats" veya "Total PnL" görünene kadar bekle
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
    Tarih butonunu bul, tıkla, 'Tüm geçmiş' seç.
    Strateji paneli screenshot'tan: takvim ikonu yanında tarih metni olan buton.
    """
    # Tarih butonunu JS ile bul — strateji paneli içinde, tarih/takvim içeren buton
    clicked = await page.evaluate("""
        () => {
            // Strateji raporu panelini bul
            const panels = document.querySelectorAll('[class*="backtesting"], [class*="strategyReport"], [class*="report"]');
            for (const panel of panels) {
                const btns = panel.querySelectorAll('button');
                for (const btn of btns) {
                    const t = btn.innerText || '';
                    // Tarih içeren buton: "22 Eyl 2025", "23 Mar 2026" gibi
                    if (/\\d{4}/.test(t) && t.length < 80) {
                        btn.click();
                        return 'panel-btn: ' + t.trim().slice(0, 50);
                    }
                }
            }
            // Fallback: tüm sayfa
            const allBtns = document.querySelectorAll('button');
            for (const btn of allBtns) {
                const t = btn.innerText || '';
                if (/\\d{4}/.test(t) && t.includes('—') && t.length < 80) {
                    btn.click();
                    return 'fallback-btn: ' + t.trim().slice(0, 50);
                }
            }
            return null;
        }
    """)

    if clicked:
        print(f"  Tarih butonu bulundu: {clicked}")
        await asyncio.sleep(1.5)
    else:
        print("  ⚠️ Tarih butonu bulunamadı")
        return

    # Dropdown'dan "Tüm geçmiş" seç — sadece görünür (visible) elementlere bak
    result = await page.evaluate("""
        () => {
            const targets = ['Tüm geçmiş', 'Tüm Geçmiş', 'All history', 'All History'];

            // Görünür olan elementleri filtrele
            function isVisible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && r.top >= 0 && r.top < window.innerHeight;
            }

            // Önce popup/overlay/dropdown container'larını ara
            const popupSels = [
                '[class*="popup"]', '[class*="dropdown"]', '[class*="menu"]',
                '[class*="overlay"]', '[class*="dialog"]', '[role="listbox"]',
                '[class*="dateRange"]', '[class*="period"]'
            ];
            for (const sel of popupSels) {
                const containers = document.querySelectorAll(sel);
                for (const container of containers) {
                    if (!isVisible(container)) continue;
                    const items = container.querySelectorAll('li, div, span, button');
                    for (const item of items) {
                        if (!isVisible(item)) continue;
                        const t = (item.innerText || '').trim();
                        if (targets.includes(t)) {
                            item.click();
                            return 'OK: ' + t;
                        }
                    }
                }
            }

            // Fallback: tüm visible li/option elementleri
            const texts = [];
            const allEls = document.querySelectorAll('li, [role="option"], [role="menuitem"]');
            for (const el of allEls) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || '').trim();
                if (t.length === 0 || t.length > 50) continue;
                texts.push(t);
                if (targets.includes(t)) {
                    el.click();
                    return 'OK-fallback: ' + t;
                }
            }
            return 'MISS: ' + JSON.stringify(texts.slice(0, 15));
        }
    """)
    await asyncio.sleep(2)
    print(f"  Dropdown sonucu: {result}")

    # Seçim başarısızsa dropdown'u kapat
    if result and not result.startswith('OK'):
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

async def get_report_values(page):
    """
    Strateji raporunu DOM'dan direkt oku — innerText yerine spesifik elementleri hedef al.
    """
    result = await page.evaluate("""
        () => {
            const res = {net_profit: 'N/A', max_drawdown: 'N/A', win_rate: 'N/A', trades: 'N/A'};

            // Strateji panelini bul
            let panel = null;
            for (const sel of ['[class*="backtesting"]', '[class*="strategyReport"]', '[class*="report"]']) {
                const el = document.querySelector(sel);
                if (el && el.innerText && el.innerText.length > 100) {
                    panel = el;
                    break;
                }
            }
            if (!panel) panel = document.body;

            const text = panel.innerText;
            const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];

                // Net Profit / Total PnL
                if (res.net_profit === 'N/A' && (line.includes('Total PnL') || line.includes('Toplam K'))) {
                    for (let o = 1; o <= 5; o++) {
                        if (i+o >= lines.length) break;
                        const v = lines[i+o];
                        if (v.includes('%')) {
                            const parts = v.split(/\\s+/);
                            for (const p of parts) {
                                if (p.includes('%')) {
                                    res.net_profit = p.replace('%','').replace(',','.').replace('−','-').replace('−','-');
                                    break;
                                }
                            }
                            break;
                        }
                    }
                }

                // Max Drawdown
                if (res.max_drawdown === 'N/A' && (line.includes('Max drawdown') || line.includes('Maksimum'))) {
                    for (let o = 1; o <= 5; o++) {
                        if (i+o >= lines.length) break;
                        const v = lines[i+o];
                        if (v.includes('%')) {
                            const parts = v.split(/\\s+/);
                            for (const p of parts) {
                                if (p.includes('%')) {
                                    res.max_drawdown = p.replace('%','').replace(',','.').replace('−','-');
                                    break;
                                }
                            }
                            break;
                        }
                    }
                }

                // Win Rate + Trades (Karlı işlemler: "60,00%" sonra "9/15")
                if ((res.win_rate === 'N/A' || res.trades === 'N/A') && line.includes('Karlı işlemler')) {
                    for (let o = 1; o <= 6; o++) {
                        if (i+o >= lines.length) break;
                        const v = lines[i+o];
                        if (v.includes('%') && res.win_rate === 'N/A') {
                            const parts = v.split(/\\s+/);
                            for (const p of parts) {
                                if (p.includes('%')) {
                                    res.win_rate = p.replace('%','').replace(',','.');
                                    break;
                                }
                            }
                        }
                        if (v.includes('/') && res.trades === 'N/A') {
                            const parts = v.split(/\\s+/);
                            for (const p of parts) {
                                if (p.includes('/')) {
                                    const total = p.split('/').pop();
                                    if (/^\\d+$/.test(total)) {
                                        res.trades = total;
                                        break;
                                    }
                                }
                            }
                        }
                        if (res.win_rate !== 'N/A' && res.trades !== 'N/A') break;
                    }
                }
            }
            return res;
        }
    """)
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
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
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

                # Rapor yüklensin
                loaded = await wait_for_report(page, "(ilk yükleme)")

                if loaded:
                    # Tüm geçmişi seç
                    await set_all_history(page)
                    # Rapor yeniden hesaplansın
                    await asyncio.sleep(3)
                    await wait_for_report(page, "(tüm geçmiş)")

                res = await get_report_values(page)

                if i == 0:
                    await page.screenshot(path="results/backtest_data.png")

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
