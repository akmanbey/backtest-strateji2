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
    Tarih butonunu bul, scroll into view yap, tam ortasına mouse click at.
    """
    # Butonu bul, scroll et, koordinatları al
    btn_rect = await page.evaluate("""
        () => {
            const panels = document.querySelectorAll('[class*="backtesting"], [class*="strategyReport"], [class*="report"]');
            for (const panel of panels) {
                for (const btn of panel.querySelectorAll('button')) {
                    const t = btn.innerText || '';
                    if (t.includes('\u2014') && /\d{4}/.test(t) && t.length < 80) {
                        btn.scrollIntoView({block: 'center', inline: 'center'});
                        const r = btn.getBoundingClientRect();
                        return {x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2), text: t.trim().slice(0,50), w: r.width, h: r.height};
                    }
                }
            }
            return null;
        }
    """)

    if not btn_rect:
        print("  ⚠️ Tarih butonu bulunamadı")
        return

    print(f"  Tarih butonu: {btn_rect['text']} @ ({btn_rect['x']},{btn_rect['y']}) size:{btn_rect['w']}x{btn_rect['h']}")
    await asyncio.sleep(0.5)

    # Tam ortasına tıkla
    await page.mouse.move(btn_rect['x'], btn_rect['y'])
    await asyncio.sleep(0.3)
    await page.mouse.down()
    await asyncio.sleep(0.1)
    await page.mouse.up()
    await asyncio.sleep(2)

    # Debug: ilk sembol için screenshot al
    try:
        await page.screenshot(path="results/dropdown_debug.png")
    except:
        pass

    # Dropdown açıldı mı kontrol et
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

    # Görünür li'leri logla
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

    print(f"  ⚠️ Dropdown açılmadı. li'ler: {found_texts[:10]}")
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)

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
    Tarih butonunu class=activeArea ile bul, koordinatına tıkla.
    """
    # activeArea class'ına sahip tarih elementini bul
    btn_info = await page.evaluate("""
        () => {
            // activeArea class'lı element — tarih metni içeren
            const els = document.querySelectorAll('[class*="activeArea"]');
            for (const el of els) {
                const t = el.innerText || '';
                if (t.includes('\u2014') && /\d{4}/.test(t) && t.length < 80) {
                    const r = el.getBoundingClientRect();
                    return {x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2), text: t.trim().slice(0,50), tag: el.tagName};
                }
            }
            return null;
        }
    """)

    if not btn_info:
        print("  ⚠️ activeArea tarih elementi bulunamadı")
        return

    print(f"  Tarih elementi: '{btn_info['text']}' tag={btn_info['tag']} @ ({btn_info['x']},{btn_info['y']})")

    # Koordinata mouse click
    await page.mouse.click(btn_info['x'], btn_info['y'])
    await asyncio.sleep(2)

    # Screenshot al — dropdown açıldı mı?
    await page.screenshot(path="results/dropdown_debug.png")

    # Dropdown'dan "Tüm geçmiş" seç
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

    # Görünür li'leri logla
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

    print(f"  ⚠️ Dropdown açılmadı. li'ler: {found_texts[:10]}")
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)

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
    Tarih butonunu bul, scroll into view yap, tam ortasına mouse click at.
    """
    # Butonu bul, scroll et, koordinatları al
    btn_rect = await page.evaluate("""
        () => {
            const panels = document.querySelectorAll('[class*="backtesting"], [class*="strategyReport"], [class*="report"]');
            for (const panel of panels) {
                for (const btn of panel.querySelectorAll('button')) {
                    const t = btn.innerText || '';
                    if (t.includes('\u2014') && /\d{4}/.test(t) && t.length < 80) {
                        btn.scrollIntoView({block: 'center', inline: 'center'});
                        const r = btn.getBoundingClientRect();
                        return {x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2), text: t.trim().slice(0,50), w: r.width, h: r.height};
                    }
                }
            }
            return null;
        }
    """)

    if not btn_rect:
        print("  ⚠️ Tarih butonu bulunamadı")
        return

    print(f"  Tarih butonu: {btn_rect['text']} @ ({btn_rect['x']},{btn_rect['y']}) size:{btn_rect['w']}x{btn_rect['h']}")
    await asyncio.sleep(0.5)

    # Tam ortasına tıkla
    await page.mouse.move(btn_rect['x'], btn_rect['y'])
    await asyncio.sleep(0.3)
    await page.mouse.down()
    await asyncio.sleep(0.1)
    await page.mouse.up()
    await asyncio.sleep(2)

    # Debug: ilk sembol için screenshot al
    try:
        await page.screenshot(path="results/dropdown_debug.png")
    except:
        pass

    # Dropdown açıldı mı kontrol et
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

    # Görünür li'leri logla
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

    print(f"  ⚠️ Dropdown açılmadı. li'ler: {found_texts[:10]}")
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)

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
        
