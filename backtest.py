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
    print("Cookie ile giriş yapılıyor...")
    await context.add_cookies([
        {
            "name":     "sessionid",
            "value":    TV_SESSIONID,
            "domain":   ".tradingview.com",
            "path":     "/",
            "secure":   True,
            "httpOnly": True,
            "sameSite": "None"
        },
        {
            "name":     "sessionid_sign",
            "value":    TV_SESSIONID_SIGN,
            "domain":   ".tradingview.com",
            "path":     "/",
            "secure":   True,
            "httpOnly": True,
            "sameSite": "None"
        }
    ])
    print("Cookie eklendi ✅")

async def wait_for_report(page):
    """Raporun hesaplanmasını bekle."""
    try:
        await page.wait_for_selector(
            'text="Rapor güncelleniyor"',
            timeout=5000
        )
        print("  Rapor hesaplanıyor...")
        await page.wait_for_selector(
            'text="Rapor güncelleniyor"',
            state="hidden",
            timeout=180000
        )
        print("  Rapor hazır ✅")
    except:
        await asyncio.sleep(4)

async def set_all_history(page):
    """
    Yeni TradingView UI: tarih aralığı butonu (ör: '23 Mar 2026 — 7 Haz 2026')
    tıklanıp açılan dropdown'dan 'Tüm geçmiş' seçilir.
    """

    # 1) Tarih aralığı butonunu bul — yeni UI'da takvim ikonu + tarih metni olan buton
    date_btn_selectors = [
        # Yeni UI: strateji paneli içindeki tarih butonu
        '[class*="backtesting"] button[class*="date"]',
        '[class*="backtesting"] button[class*="period"]',
        '[class*="backtesting"] button[class*="range"]',
        # Takvim ikonu içeren buton
        'button:has(svg[data-icon="calendar"])',
        'button:has([data-icon="date-range"])',
        # Tarih metni içeren buton (Mar, Jan, Haz, Jun vs.)
        'button:has-text("Mar"), button:has-text("Jan"), button:has-text("Feb"), '
        'button:has-text("Apr"), button:has-text("May"), button:has-text("Jun"), '
        'button:has-text("Jul"), button:has-text("Aug"), button:has-text("Sep"), '
        'button:has-text("Oct"), button:has-text("Nov"), button:has-text("Dec")',
        # Eski UI fallback
        '[data-name="date-ranges-button"]',
    ]

    clicked = False
    for sel in date_btn_selectors:
        try:
            locator = page.locator(sel).first
            count = await locator.count()
            if count > 0:
                await locator.click(timeout=3000)
                await asyncio.sleep(1.5)
                clicked = True
                print(f"  Tarih butonu tıklandı: {sel[:60]}")
                break
        except:
            continue

    if not clicked:
        # JS ile takvim/tarih içeren butonu bul
        try:
            await page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const dateBtn = btns.find(b => {
                        const t = b.innerText || '';
                        return /\\d{4}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Haz|Oca|Şub|Mar|Nis|May|Tem|Ağu|Eyl|Eki|Kas|Ara/.test(t) && t.length < 60;
                    });
                    if (dateBtn) dateBtn.click();
                }
            """)
            await asyncio.sleep(1.5)
            clicked = True
            print("  Tarih butonu JS ile tıklandı")
        except:
            pass

    if not clicked:
        print("  ⚠️ Tarih butonu bulunamadı, devam ediliyor")
        return

    # 2) Dropdown'dan "Tüm geçmiş" seç — bu seçilince TradingView otomatik DEEP'e geçer
    all_history_texts = [
        'Tüm geçmiş', 'Tüm Geçmiş', 'All history', 'All History', 'Max', 'All', 'Tümü'
    ]
    for text in all_history_texts:
        try:
            # Exact text match — has-text yerine filter ile
            for item_sel in [
                f'[role="option"]',
                f'[role="menuitem"]',
                f'li',
                f'div[class*="item"]',
            ]:
                items = page.locator(item_sel).filter(has_text=text)
                count = await items.count()
                for idx in range(count):
                    item = items.nth(idx)
                    item_text = await item.inner_text()
                    if item_text.strip() == text:
                        await item.click(timeout=3000)
                        await asyncio.sleep(2)
                        print(f'  "{text}" seçildi ✅')
                        return
        except:
            continue

    # 3) JS fallback — dropdown içinde metne göre tıkla
    try:
        await page.evaluate("""
            () => {
                const keywords = ['Tüm geçmiş', 'Tüm Geçmiş', 'All history', 'All History', 'Max', 'All', 'Tümü'];
                const allEls = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"], li, div'));
                for (const kw of keywords) {
                    const el = allEls.find(e => e.innerText && e.innerText.trim() === kw);
                    if (el) { el.click(); return; }
                }
            }
        """)
        await asyncio.sleep(2)
        print("  Tüm geçmiş JS ile seçildi ✅")
    except Exception as e:
        print(f"  ⚠️ Tüm geçmiş seçilemedi: {e}")

async def change_symbol(page, symbol):
    search_term = symbol.split(":")[-1]
    try:
        await page.click('[id="header-toolbar-symbol-search"]', timeout=5000)
        await asyncio.sleep(0.5)
        await page.keyboard.press("Control+A")
        await page.keyboard.type(search_term, delay=40)
        await asyncio.sleep(1.5)
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)
    except Exception as e:
        print(f"  Sembol hatası: {e}")

async def get_report_text(page):
    """Strateji raporu panelinin metnini al."""
    container_selectors = [
        '[class*="backtesting"]',
        '[class*="strategyReport"]',
        '[class*="strategy-report"]',
        '[class*="backtestingReport"]',
        '[data-name="backtesting-report"]',
    ]
    for sel in container_selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                text = await el.inner_text()
                if text and len(text) > 50:
                    return text
        except:
            continue

    # Fallback
    return await page.evaluate("() => document.body.innerText")

async def parse_report(text):
    """
    Yeni TradingView UI metriklerini parse et.
    Yeni UI:  Total PnL / Max drawdown / Karlı işlemler XX/YY / Kar faktörü
    Eski UI:  Toplam K&Z / Maksimum öz sermaye / Karlı işlemler / Toplam işlemler
    """
    res = {
        "net_profit":   "N/A",
        "max_drawdown": "N/A",
        "win_rate":     "N/A",
        "trades":       "N/A"
    }

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    def clean_pct(v):
        return v.replace("%", "").replace(" ", "").replace("\xa0", "").strip()

    for j, line in enumerate(lines):

        # ── Net Kar / Total PnL ──────────────────────────────────────────
        if res["net_profit"] == "N/A":
            if any(k in line for k in ["Total PnL", "Toplam K&Z", "Toplam K/Z", "Net Profit", "Net kar"]):
                # Yeni UI: değer aynı satırda veya hemen sonrasında, % içeriyor
                for offset in range(0, 5):
                    if j + offset < len(lines):
                        val = lines[j + offset]
                        # "−19,62 USDT −0,98%" gibi — % olan token'ı al
                        if "%" in val:
                            pct = [t for t in val.split() if "%" in t]
                            if pct:
                                res["net_profit"] = clean_pct(pct[0])
                                break
                        # Sadece sayısal değer (eski UI)
                        if offset > 0 and val.replace(",","").replace(".","").replace("-","").replace("−","").isdigit():
                            res["net_profit"] = clean_pct(val)
                            break

        # ── Max Drawdown ─────────────────────────────────────────────────
        if res["max_drawdown"] == "N/A":
            if any(k in line for k in ["Max drawdown", "Maksimum öz sermaye", "Max Drawdown", "Maks."]):
                for offset in range(0, 5):
                    if j + offset < len(lines):
                        val = lines[j + offset]
                        if "%" in val:
                            pct = [t for t in val.split() if "%" in t]
                            if pct:
                                res["max_drawdown"] = clean_pct(pct[0])
                                break
                        if offset > 0 and val.replace(",","").replace(".","").replace("-","").replace("−","").isdigit():
                            res["max_drawdown"] = clean_pct(val)
                            break

        # ── Win Rate / Karlı işlemler ────────────────────────────────────
        # Yeni UI: "Karlı işlemler" satırı, değer: "64,71% 22/34"
        if res["win_rate"] == "N/A" or res["trades"] == "N/A":
            if any(k in line for k in ["Karlı işlemler", "Percent Profitable", "Kazanma oranı"]):
                for offset in range(0, 4):
                    if j + offset < len(lines):
                        val = lines[j + offset]
                        # "64,71% 22/34" formatı
                        if "%" in val and "/" in val:
                            parts = val.split()
                            for part in parts:
                                if "%" in part and res["win_rate"] == "N/A":
                                    res["win_rate"] = clean_pct(part)
                                if "/" in part and res["trades"] == "N/A":
                                    # "22/34" → toplam = 34
                                    total = part.split("/")[-1]
                                    res["trades"] = total
                            break
                        # Sadece % (eski UI)
                        if "%" in val and res["win_rate"] == "N/A":
                            pct = [t for t in val.split() if "%" in t]
                            if pct:
                                res["win_rate"] = clean_pct(pct[0])
                            break

        # ── Toplam İşlem (eski UI fallback) ─────────────────────────────
        if res["trades"] == "N/A":
            if any(k in line for k in ["Toplam işlemler", "Total Trades", "Toplam kapalı"]):
                for offset in range(1, 4):
                    if j + offset < len(lines):
                        val = lines[j + offset].strip()
                        if val.replace(" ","").isdigit():
                            res["trades"] = val
                            break

    return res

async def get_results(page, symbol_idx):
    res_default = {
        "net_profit":   "N/A",
        "max_drawdown": "N/A",
        "win_rate":     "N/A",
        "trades":       "N/A"
    }
    try:
        await set_all_history(page)
        await wait_for_report(page)

        text = await get_report_text(page)
        res = await parse_report(text)

        # İlk sembolde debug için ham metni göster
        if symbol_idx == 0:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            print(f"  [DEBUG] Toplam satır: {len(lines)}")
            print(f"  [DEBUG] İlk 80 satır: {lines[:80]}")

        return res
    except Exception as e:
        print(f"  Veri hatası: {e}")
        return res_default

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
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
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
                res = await get_results(page, i)

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
                    "Sembol":         clean,
                    "Net Kar %":      "HATA",
                    "Max Drawdown %": "HATA",
                    "Win Rate %":     "HATA",
                    "İşlem Sayısı":   "HATA",
                })

            if (i + 1) % 20 == 0:
                save_csv(all_results)
                print(f"  💾 Ara kayıt: {i+1} sembol")

        await browser.close()

    save_csv(all_results)
    print(f"\nTamamlandı → {OUTPUT_FILE}")

asyncio.run(main())
