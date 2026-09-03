"""Adversarial stress test for Challenge 2: Playwright Chromium Headless Execution."""
import asyncio
import os
import subprocess
import sys
import time
import pytest
from playwright.async_api import async_playwright


def _get_headless_chromium_pids() -> set[str]:
    res = subprocess.run(["pgrep", "-f", "chromium.*--headless"], capture_output=True, text=True)
    if res.returncode == 0 and res.stdout.strip():
        return set(res.stdout.strip().split())
    return set()

@pytest.mark.asyncio
async def test_concurrent_headless_contexts_under_stress():
    """Verify that multiple concurrent browser contexts and pages execute and render without deadlock or crash."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        
        async def run_worker(worker_id: int):
            for step in range(4):
                context = await browser.new_context(viewport={"width": 1280, "height": 720})
                page = await context.new_page()
                
                # Render complex DOM
                html = (
                    "<html><body>"
                    f"<h1>Worker {worker_id} Step {step}</h1>"
                    "<div class='grid'>"
                    + "".join(f"<div class='card' data-idx='{i}'><span class='title'>Card {i}</span><p>Content {i*2}</p></div>" for i in range(250))
                    + "</div>"
                    "</body></html>"
                )
                await page.set_content(html)
                
                # DOM queries and evaluations
                card_count = await page.evaluate("() => document.querySelectorAll('.card').length")
                assert card_count == 250, f"Worker {worker_id} expected 250 cards, got {card_count}"
                
                title_text = await page.inner_text(".card[data-idx='125'] .title")
                assert title_text == "Card 125"
                
                # In-memory screenshot
                img_data = await page.screenshot(type="png", full_page=False)
                assert len(img_data) > 500, f"Screenshot data too small: {len(img_data)}"
                
                await page.close()
                await context.close()

        # Run 6 parallel workers -> 24 complete rendering cycles
        workers = [run_worker(i) for i in range(6)]
        await asyncio.gather(*workers)
        
        await browser.close()

@pytest.mark.asyncio
async def test_page_error_and_timeout_resilience():
    """Verify that JS errors, aborts, and timeouts inside pages do not crash the browser engine."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Inject intentional JS syntax / runtime error in page
        await page.set_content("<html><body><script>throw new Error('Adversarial JS Error');</script><h1>Error Handled</h1></body></html>")
        h1_text = await page.inner_text("h1")
        assert h1_text == "Error Handled"

        # Test evaluation throwing error in Python
        with pytest.raises(Exception):
            await page.evaluate("() => { throw new Error('Eval crash test'); }")

        # Page should still be alive and responsive
        eval_result = await page.evaluate("() => 40 + 2")
        assert eval_result == 42

        await page.close()
        await context.close()
        await browser.close()

@pytest.mark.asyncio
async def test_multiple_viewports_and_screenshot_rendering():
    """Verify accurate rendering across multiple standard viewports."""
    viewports = [
        {"width": 375, "height": 812, "name": "mobile"},
        {"width": 1080, "height": 1920, "name": "shorts_vertical"},
        {"width": 1920, "height": 1080, "name": "horizontal_fhd"},
    ]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for vp in viewports:
            context = await browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = await context.new_page()
            await page.set_content(f"""
                <div style="width: 100%; height: 100vh; background: #111; color: #fff; display: flex; align-items: center; justify-content: center;">
                    <h2>Resolution {vp['width']}x{vp['height']}</h2>
                </div>
            """)
            screenshot = await page.screenshot(type="jpeg", quality=80)
            assert len(screenshot) > 1000
            await page.close()
            await context.close()
        await browser.close()

def test_no_zombie_chromium_processes():
    """Verify all browser instances properly terminate without leaving orphaned processes."""
    pids_before = _get_headless_chromium_pids()
    # Run a quick isolated subprocess
    subprocess.run([
        sys.executable, "-c",
        "import asyncio\nfrom playwright.async_api import async_playwright\n"
        "async def m():\n"
        "  async with async_playwright() as p:\n"
        "    b = await p.chromium.launch(headless=True)\n"
        "    await b.close()\n"
        "asyncio.run(m())\n"
    ], check=True)
    time.sleep(0.5)
    # Check running chromium processes
    pids_after = _get_headless_chromium_pids()
    leaked = pids_after - pids_before
    assert len(leaked) == 0, f"Detected newly leaked chromium processes: {leaked}"

if __name__ == "__main__":
    pytest.main(["-v", __file__])
