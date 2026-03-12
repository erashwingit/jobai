"""
modules/application/browser_config.py — Playwright stealth browser configuration.
Security: Removes webdriver flags and applies anti-detection measures.

⚠️  IMPORTANT: Run browser automation LOCALLY, never on GitHub Actions.
    Datacenter IPs are immediately flagged by LinkedIn, Naukri, and Indeed.
"""
import asyncio
import random
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright


async def get_stealth_browser(
    pw: Playwright | None = None,
    headless: bool = True,
    portal: str | None = None,
) -> tuple[Browser, BrowserContext]:
    """
    Create a Playwright browser with stealth configuration.
    Removes automation indicators and mimics a real user browser.

    Args:
        pw: Existing Playwright instance (creates new one if None)
        headless: Run headless (True) or visible (False for debugging)
        portal: Optional portal name for session loading

    Returns:
        Tuple of (Browser, BrowserContext)
    """
    if pw is None:
        pw = await async_playwright().start()

    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--disable-extensions",
            "--window-size=1920,1080",
            "--disable-notifications",
            "--disable-popup-blocking",
        ],
    )

    context_options: dict = {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "extra_http_headers": {
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    }

    # Load saved session if available (reduces login frequency)
    if portal:
        from modules.application.session_manager import load_session
        context_options = await load_session(context_options, portal)

    context = await browser.new_context(**context_options)

    # Remove webdriver detection flags
    await context.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

        // Add realistic plugins array
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                {name: 'Native Client', filename: 'internal-nacl-plugin'},
            ]
        });

        // Add languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-IN', 'en-US', 'en']
        });

        // Add chrome runtime object
        window.chrome = {
            runtime: {
                id: 'notarealid',
                connect: function() {},
                sendMessage: function() {},
            }
        };

        // Override permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({state: 'denied'}) :
                originalQuery(parameters)
        );
    """)

    return browser, context


async def human_delay(min_s: float = 2.0, max_s: float = 8.0) -> None:
    """Simulate human-like random delay between actions."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)


async def human_type(page, selector: str, text: str) -> None:
    """
    Type text with human-like character-by-character delays.
    Avoids instantly filling form fields which triggers bot detection.
    """
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.2, 0.5))

    for char in text:
        await page.keyboard.type(char)
        # Variable typing speed: fast for common chars, slower for others
        delay = random.gauss(0.08, 0.03)
        await asyncio.sleep(max(0.02, delay))


async def human_scroll(page, direction: str = "down", amount: int = 300) -> None:
    """Scroll page with human-like speed."""
    scroll_y = amount if direction == "down" else -amount
    await page.evaluate(f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})")
    await asyncio.sleep(random.uniform(0.5, 1.5))
