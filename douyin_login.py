#!/usr/bin/env python3
"""Douyin (抖音) login helper — headless QR code screenshot + storage_state save.

Run on the SBC:
  python3 douyin_login.py

Outputs:
  /tmp/douyin_qr.png  — QR code screenshot for the user to scan
  ~/sau/cookies/douyin_uploader/douyin_main.json — Playwright storage_state
"""
import asyncio
import os
import sys
import json
from pathlib import Path

# Ensure sau conf is importable
sys.path.insert(0, os.path.expanduser("~/sau"))

from patchright.async_api import async_playwright

COOKIE_PATH = os.path.expanduser("~/sau/cookies/douyin_uploader/douyin_main.json")
QR_SCREENSHOT = "/tmp/douyin_qr.png"
LOGIN_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_HOME = "https://creator.douyin.com"
TIMEOUT_SEC = 600  # 10 minutes to scan

QR_SELECTORS = [
    'div#animate_qrcode_container img[src^="data:image"]',
    'div[class*="animate_qrcode_container"] img[src^="data:image"]',
    'div[class*="scan_qrcode_login_content"] img[src^="data:image"]',
    'img[aria-label="二维码"]',
]


async def main():
    os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="chromium",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        print("[1/5] Navigating to creator.douyin.com...", flush=True)
        await page.goto(DOUYIN_HOME, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        # Check if already logged in (unlikely with fresh context)
        if "creator-micro" in page.url:
            print("[SKIP] Already logged in, saving state...", flush=True)
            await context.storage_state(path=COOKIE_PATH)
            print(f"[DONE] Saved to {COOKIE_PATH}", flush=True)
            await browser.close()
            return

        print("[2/5] Waiting for QR code to appear...", flush=True)
        # Wait for login page to fully load
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # Try to click "扫码登录" tab if present
        try:
            scan_tab = page.get_by_text("扫码登录", exact=True).first
            await scan_tab.wait_for(state="attached", timeout=10000)
            try:
                await scan_tab.click(timeout=3000)
                await asyncio.sleep(1)
            except Exception:
                pass
        except Exception:
            print("[WARN] No '扫码登录' tab found, continuing...", flush=True)

        # Extract QR code screenshot
        print("[3/5] Capturing QR code screenshot...", flush=True)
        qr_captured = False
        for sel in QR_SELECTORS:
            try:
                qr = page.locator(sel).first
                await qr.wait_for(state="attached", timeout=10000)
                # Take screenshot of just the QR element
                try:
                    await qr.screenshot(path=QR_SCREENSHOT)
                    qr_captured = True
                    print(f"[OK] QR screenshot saved to {QR_SCREENSHOT} (selector: {sel})", flush=True)
                    break
                except Exception:
                    # Fall back to full page screenshot
                    pass
            except Exception:
                continue

        if not qr_captured:
            # Full page screenshot as fallback
            await page.screenshot(path=QR_SCREENSHOT, full_page=False)
            print(f"[WARN] QR element not found, full page screenshot saved to {QR_SCREENSHOT}", flush=True)

        # Also save QR as data URL for terminal display
        for sel in QR_SELECTORS:
            try:
                qr = page.locator(sel).first
                src = await qr.get_attribute("src")
                if src:
                    with open("/tmp/douyin_qr_dataurl.txt", "w") as f:
                        f.write(src)
                    print(f"[INFO] QR data URL saved", flush=True)
                    break
            except Exception:
                continue

        print(f"[4/5] Waiting for login (up to {TIMEOUT_SEC}s)...", flush=True)
        logged_in = False
        poll_interval = 3
        elapsed = 0

        while elapsed < TIMEOUT_SEC:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # Check URL change to creator-micro
            current_url = page.url
            if "creator-micro" in current_url:
                # Verify no login markers visible
                has_login_ui = False
                for marker_text in ["扫码登录", "手机号登录"]:
                    try:
                        if await page.get_by_text(marker_text, exact=True).first.is_visible():
                            has_login_ui = True
                            break
                    except Exception:
                        continue
                if not has_login_ui:
                    logged_in = True
                    break

            if elapsed % 30 == 0:
                print(f"  ...still waiting ({elapsed}s elapsed, url: {current_url[:60]})", flush=True)

        if logged_in:
            print("[5/5] Login detected! Saving storage_state...", flush=True)
            await asyncio.sleep(2)
            await context.storage_state(path=COOKIE_PATH)

            # Verify sessionid exists
            with open(COOKIE_PATH, "r") as f:
                state = json.load(f)
            cookie_names = [c["name"] for c in state.get("cookies", [])]
            has_session = "sessionid" in cookie_names
            print(f"[DONE] Saved {len(cookie_names)} cookies to {COOKIE_PATH}", flush=True)
            print(f"[INFO] sessionid present: {has_session}", flush=True)
            if not has_session:
                print("[WARN] sessionid not found — cookie may not work!", flush=True)
        else:
            print(f"[TIMEOUT] Login not detected within {TIMEOUT_SEC}s", flush=True)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
