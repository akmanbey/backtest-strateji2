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
        await asyncio.sleep(3)

async def set_all_history(page):
    try:
        await page.click('[data-name="date-ranges-button"]', timeout=5000)
        await asyncio.sleep(1.5)
        await page.click('text="Tüm geçmiş"', timeout=5000)
        await asyncio.sleep(2)
        print("  Tüm geçmiş seçildi ✅")
    except:
        try:
            await page.click(
                '[class*="strategyReport"] [class*="dateRange"], '
                '[class*="backtesting"] [class*="dateRange"]',
                timeout=5000
            )
            await asyncio.sleep(1.5)
            await page.click('text="Tüm geçmiş"', timeout=5000)
            await asyncio.sleep(2)
            print("  Tüm geçmiş seçildi ✅")
        except:
            try:
                await page.click('[data-name="date-ranges-button"]', timeout=3000)
                await asyncio.sleep(1.5)
                await page.click('text="All"', timeout=3000)
                await asyncio.sleep(2)
                print("  All history seçildi ✅")
            except Exception as e:
                print(f"  Tüm geçmiş seçilemedi: {e}")

async def change_symbol(page, symbol):
    search_term = symbol.split(":")[-1]
    try:
        await page.click('[id="header-toolbar-symbol-search"]', timeout=5000)
        await asyncio.sleep(0.5)
        await page.keyboard.press("Control+A")
        await page.keyboard.type(search_term, delay=40)
        await asyncio.sleep(1.5)
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"  Sembol hatası: {e}")

async def get_results(page):
    res = {
        "net_profit":   "N/A",
        "max_drawdown": "N/A",
        "win_rate":     "N/A",
        "trades":       "N/A"
    }
    try:
        await set_all_history(page)
        await wait_for_report(page)

        all_text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in all_text.split('\n') if l.strip()]
        print(f"  Sayfa metni: {lines[:60]}")

        for j, line in enumerate(lines):
            if "Toplam K&Z" in line or "Net Profit" in line:
                if j+3 < len(lines):
                    res["net_profit"] = lines[j+3].replace("%", "").strip()
            if "Maksimum öz sermaye" in line or "Max Drawdown" in line:
                if j+3 < len(lines):
                    res["max_drawdown"] = lines[j+3].replace("%", "").strip()
            if "Karlı işlemler" in line or "Percent Profitable" in line:
                if j+1 < len(lines):
                    val = lines[j+1]
                    res["win_rate"] = val.split()[0].replace("%", "") if val != "N/A" else val
            if "Toplam işlemler" in line or "Total Trades" in line:
                if j+1 < len(lines):
                    res["trades"] = lines[j+1]

    except Exception as e:
        print(f"  Veri hatası: {e}")
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
            clean = symbol.replace("BINANCE:", "").replace(".P", "")
            print(f"\n[{i+1}/{len(symbols)}] {clean}")
            try:
                await change_symbol(page, symbol)
                res = await get_results(page)

                if i == 0:
                    await page.screenshot(path="results/backtest_data.png")

                all_results.append({
                    "Sembol":         clean,
                    "Net Kar %":      res["net_profit"],
                    "Max Drawdown %": res["max_drawdown"],
                    "Win Rate %":     res["win_rate"],
                    "İşlem Sayısı":   res["trades"],
                })
                print(f"  ✅ Kar:{res['net_profit']} | DD:{res['max_drawdown']} | Win:{res['win_rate']}")
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
