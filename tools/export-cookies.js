/**
 * tools/export-cookies.js
 * One-time manual login tool to export and encrypt session cookies.
 *
 * Run ONCE manually:
 *   node tools/export-cookies.js
 *
 * The script opens a visible browser, lets you log into LinkedIn & Naukri,
 * then encrypts the session cookies with AES-256-GCM and saves them to:
 *   ~/.config/ashvani-job-bot/cookies.enc
 *
 * After this, the bot injects cookies automatically — no passwords needed.
 */

'use strict';

const { chromium } = require('playwright');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const CONFIG_DIR = path.join(process.env.HOME, '.config', 'ashvani-job-bot');
const COOKIE_FILE = path.join(CONFIG_DIR, 'cookies.enc');

const PORTALS = [
  {
    name: 'linkedin',
    loginUrl: 'https://www.linkedin.com/login',
    waitFor: 'https://www.linkedin.com/feed',
    successSelector: '.global-nav__me',
    instructions: 'Log into LinkedIn in the browser window, then press Enter here.',
  },
  {
    name: 'naukri',
    loginUrl: 'https://www.naukri.com/nlogin/login',
    waitFor: 'https://www.naukri.com',
    successSelector: '.nI-gNb-user-info__picture',
    instructions: 'Log into Naukri in the browser window, then press Enter here.',
  },
];

async function main() {
  const cookieSecret = process.env.COOKIE_SECRET;
  if (!cookieSecret || cookieSecret.length < 16) {
    console.error('\n[ERROR] COOKIE_SECRET environment variable is required (min 16 chars).');
    console.error('Add to .env: COOKIE_SECRET=your_32_char_secret_here\n');
    process.exit(1);
  }

  console.log('\n╔══════════════════════════════════════════════════════╗');
  console.log('║    Ashvani Job Bot — Cookie Export Tool              ║');
  console.log('╚══════════════════════════════════════════════════════╝\n');
  console.log('This tool opens a visible browser for you to log in manually.');
  console.log('Your passwords are NEVER stored — only encrypted session cookies.\n');

  fs.mkdirSync(CONFIG_DIR, { recursive: true, mode: 0o700 });

  const allCookies = {};

  // Launch visible (non-headless) browser for manual login
  const browser = await chromium.launch({ headless: false, slowMo: 100 });

  for (const portal of PORTALS) {
    console.log(`\n── ${portal.name.toUpperCase()} ──────────────────────────`);
    console.log(portal.instructions);

    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36',
    });
    const page = await context.newPage();

    await page.goto(portal.loginUrl, { waitUntil: 'networkidle' });

    // Wait for user to log in manually
    await waitForEnter(`\nPress ENTER after you have successfully logged into ${portal.name}...`);

    // Verify login
    const isLoggedIn = await page.$(portal.successSelector).catch(() => null);
    if (!isLoggedIn) {
      console.warn(`[WARNING] Could not verify ${portal.name} login. Saving cookies anyway.`);
    } else {
      console.log(`✓ ${portal.name} login verified`);
    }

    // Extract all cookies
    const cookies = await context.cookies();
    allCookies[portal.name] = cookies;
    console.log(`  Captured ${cookies.length} cookies for ${portal.name}`);

    await context.close();
  }

  await browser.close();

  // Encrypt with AES-256-GCM
  const salt = crypto.randomBytes(16).toString('hex');
  const iv = crypto.randomBytes(12);
  const key = crypto.scryptSync(cookieSecret, salt, 32, { N: 65536 }); // OWASP minimum

  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const plaintext = JSON.stringify(allCookies);

  const encrypted = Buffer.concat([
    cipher.update(plaintext, 'utf8'),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();

  const payload = {
    version: 1,
    algorithm: 'aes-256-gcm',
    salt,
    iv: iv.toString('hex'),
    tag: tag.toString('hex'),
    data: encrypted.toString('hex'),
    exported_at: new Date().toISOString(),
    portals: Object.keys(allCookies),
  };

  fs.writeFileSync(COOKIE_FILE, JSON.stringify(payload, null, 2), { mode: 0o600 });

  console.log('\n╔══════════════════════════════════════════════════════╗');
  console.log('║              Cookies Exported Successfully!          ║');
  console.log('╚══════════════════════════════════════════════════════╝');
  console.log(`\n  Saved to: ${COOKIE_FILE}`);
  console.log(`  Portals:  ${payload.portals.join(', ')}`);
  console.log(`  Exported: ${payload.exported_at}\n`);
  console.log('  The bot will now use these cookies automatically.');
  console.log('  Re-run this script if you ever get logged out.\n');
}

function waitForEnter(message) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(message, () => { rl.close(); resolve(); });
  });
}

main().catch(err => {
  console.error('\n[FATAL]', err.message);
  process.exit(1);
});
