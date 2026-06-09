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
        await asyncio.sleep(3)
        # Header'da doğru sembolün yüklendiğini doğrula
        await wait_for_symbol(page, search_term)
        print(f"  Sembol: {search_term}")
    except Exception as e:
        print(f"  Sembol hatası: {e}")

async def wait_for_symbol(page, symbol_name, timeout=15):
    """Header'da doğru sembolün yüklendiğini doğrula."""
    clean = symbol_name.replace("BINANCE:", "").replace("OKX:", "").replace(".P", "")
    for _ in range(timeout):
        try:
            header = await page.evaluate("() => document.querySelector('#header-toolbar-symbol-search')?.innerText || ''")
            if clean.upper() in header.upper():
                return True
        except:
            pass
        await asyncio.sleep(1)
    print(f"  ⚠️ Header'da {clean} görünmedi")
    return False

async def wait_for_new_report(page, prev_trades, label=""):
    """Rapordaki işlem sayısının öncekinden farklı olmasını bekle."""
    for _ in range(20):
        try:
            for sel in ['[class*="backtesting"]', '[class*="strategyReport"]']:
                el = page.locator(sel).first
                if await el.count() > 0:
                    t = await el.inner_text()
                    if "Key stats" in t or "Total PnL" in t:
                        # İşlem sayısı değiştiyse yeni rapor yüklendi
                        lines = [l.strip() for l in t.split("\n") if l.strip()]
                        for i, line in enumerate(lines):
                            if "/" in line:
                                for p in line.split():
                                    if "/" in p:
                                        total = p.split("/")[-1].strip()
                                        if total.isdigit() and total != str(prev_trades):
                                            print(f"  Yeni rapor yüklendi ✅ {label}")
                                            return True
        except:
            pass
        await asyncio.sleep(1)
    print(f"  ⚠️ Yeni rapor gelmedi {label}")
    return False
    for selector in ['text="Key stats"', 'text="Total PnL"', 'text="Karlı işlemler"']:
        try:
            await page.wait_for_selector(selector, timeout=30000)
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
    # Panelin innerText'ini Python'a al, parse et
    text = None
    for sel in ['[class*="backtesting"]', '[class*="strategyReport"]', '[class*="report"]']:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                t = await el.inner_text()
                if t and len(t) > 100:
                    text = t
                    break
        except:
            continue
    if not text:
        text = await page.evaluate("() => document.body.innerText")

    res = {"net_profit": "N/A", "max_drawdown": "N/A", "win_rate": "N/A", "trades": "N/A"}
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    def get_pct(v):
        for p in v.split():
            if "%" in p:
                return p.replace("%", "").replace(",", ".").replace("\u2212", "-").replace("−", "-").strip()
        return None

    for i, line in enumerate(lines):
        if res["net_profit"] == "N/A" and ("Total PnL" in line or "Toplam K" in line):
            for o in range(1, 6):
                if i + o >= len(lines): break
                pct = get_pct(lines[i + o])
                if pct: res["net_profit"] = pct; break

        if res["max_drawdown"] == "N/A" and ("Max drawdown" in line or "Maksimum" in line):
            for o in range(1, 6):
                if i + o >= len(lines): break
                pct = get_pct(lines[i + o])
                if pct: res["max_drawdown"] = pct; break

        if (res["win_rate"] == "N/A" or res["trades"] == "N/A") and ("Karlı işlemler" in line or "Percent" in line):
            for o in range(1, 7):
                if i + o >= len(lines): break
                v = lines[i + o]
                if "%" in v and res["win_rate"] == "N/A":
                    pct = get_pct(v)
                    if pct: res["win_rate"] = pct
                if "/" in v and res["trades"] == "N/A":
                    for p in v.split():
                        if "/" in p:
                            total = p.split("/")[-1].strip()
                            if total.isdigit(): res["trades"] = total; break
                if res["win_rate"] != "N/A" and res["trades"] != "N/A": break

    return res

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

        # Daha önce kaydedilen sonuçları yükle (resume)
        done_symbols = set()
        if os.path.exists(OUTPUT_FILE):
            try:
                import csv as csv_mod
                with open(OUTPUT_FILE, newline="", encoding="utf-8-sig") as f:
                    for row in csv_mod.DictReader(f):
                        if row.get("Net Kar %") not in ("N/A", "HATA", ""):
                            done_symbols.add(row["Sembol"])
                            all_results.append(row)
                print(f"Resume: {len(done_symbols)} sembol zaten tamamlanmış, atlanıyor")
            except:
                pass

        import time
        start_time = time.time()

        for i, symbol in enumerate(symbols):
            clean = symbol.replace("BINANCE:", "").replace("OKX:", "").replace(".P", "")

            # Zaten tamamlananları atla
            if clean in done_symbols:
                print(f"[{i+1}/{len(symbols)}] {clean} - atlandı (zaten var)")
                continue

            print(f"\n[{i+1}/{len(symbols)}] {clean}")

            # Her 30 dakikada bir cookie'yi yenile — sayfa yenileme yok, session taze kalsın
            elapsed = time.time() - start_time
            if elapsed > 30 * 60:
                print("  ⏰ 30 dk geçti, cookie yenileniyor...")
                await login(context)
                start_time = time.time()
                print("  Cookie yenilendi ✅")

            try:
                await change_symbol(page, symbol)
                loaded = await wait_for_report(page, "(ilk yükleme)")

                if loaded:
                    # Tüm geçmişi seç
                    prev_trades = all_results[-1]["İşlem Sayısı"] if all_results else None
                    await set_all_history(page)
                    await asyncio.sleep(2)
                    # "Raporu güncelle" butonu çıkarsa tıkla
                    for btn_text in ['Raporu güncelle', 'Update report', 'Recalculate']:
                        try:
                            btn = page.get_by_text(btn_text, exact=True)
                            if await btn.count() > 0:
                                await btn.first.click(timeout=3000)
                                print(f'  "{btn_text}" tıklandı ✅')
                                break
                        except:
                            continue
                    # Önceki işlem sayısından farklı gelene kadar bekle
                    await wait_for_new_report(page, prev_trades, "(tüm geçmiş)")

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
