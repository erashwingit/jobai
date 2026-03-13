/**
 * services/submitter/index.js
 * Stealth Playwright job application submitter microservice.
 * POST /submit → fills Easy Apply forms using injected session cookies.
 * Port: 3002
 *
 * Uses playwright-extra + puppeteer-extra-plugin-stealth for anti-detection.
 *
 * ⚠️  CRITICAL: Run this service LOCALLY only — never on GitHub Actions.
 *    Datacenter IPs are immediately flagged by LinkedIn/Naukri.
 */

'use strict';

const express = require('express');
const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// Apply stealth plugin to playwright-extra
chromium.use(StealthPlugin());

const app = express();
app.use(express.json({ limit: '5mb' }));

// ── Health check ─────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'submitter', port: 3002 });
});

// ── POST /submit ──────────────────────────────────────────────────────────────
/**
 * Request body (JSON):
 * {
 *   "portal":       "linkedin" | "naukri" | "indeed",
 *   "job_url":      "https://...",
 *   "job_id":       "abc123",
 *   "company":      "Acme Corp",
 *   "role":         "AI Engineer",
 *   "resume_path":  "/path/to/resume.pdf",
 *   "cookie_file":  "/path/to/cookies.enc"  (optional, uses default if omitted)
 * }
 *
 * Response:
 * {
 *   "success": true,
 *   "application_id": "...",
 *   "screenshot_base64": "...",
 *   "message": "Applied successfully"
 * }
 */
app.post('/submit', async (req, res) => {
  const { portal, job_url, job_id, company, role, resume_path, cookie_file } = req.body;

  if (!portal || !job_url || !resume_path) {
    return res.status(400).json({
      success: false,
      error: 'Missing required fields: portal, job_url, resume_path',
    });
  }

  const cookiePath = cookie_file || path.resolve(
    process.env.HOME, '.config/ashvani-job-bot/cookies.enc'
  );

  // Load and decrypt cookies
  let cookies;
  try {
    cookies = loadCookies(cookiePath, portal);
  } catch (err) {
    return res.status(401).json({
      success: false,
      error: 'CookieExpiredError',
      message: `Session cookies missing or expired for ${portal}. Run: node tools/export-cookies.js`,
    });
  }

  console.log(`[submitter] Starting ${portal} application for ${company} | ${role}`);

  const browser = await chromium.launch({
    headless: true,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--disable-dev-shm-usage',
      '--no-sandbox',
      '--disable-setuid-sandbox',
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    locale: 'en-IN',
    timezoneId: 'Asia/Kolkata',
  });

  // Inject session cookies (replaces password login entirely)
  await context.addCookies(cookies);

  const page = await context.newPage();
  let screenshot = null;

  try {
    const result = await applyToJob(page, portal, job_url, resume_path);

    // Capture screenshot of final state
    const screenshotBuffer = await page.screenshot({ fullPage: false });
    screenshot = screenshotBuffer.toString('base64');

    await browser.close();

    console.log(`[submitter] ${result.success ? '✓' : '✗'} ${company} | ${role} — ${result.message}`);

    return res.json({
      success: result.success,
      application_id: result.application_id || `${portal}-${job_id}-${Date.now()}`,
      screenshot_base64: screenshot,
      message: result.message,
    });

  } catch (err) {
    console.error(`[submitter] Error for job ${job_id}:`, err.message);

    try {
      const screenshotBuffer = await page.screenshot({ fullPage: false });
      screenshot = screenshotBuffer.toString('base64');
    } catch (_) {}

    await browser.close();

    return res.status(500).json({
      success: false,
      error: err.message,
      screenshot_base64: screenshot,
      message: `Application failed: ${err.message}`,
    });
  }
});

// ── Portal-specific submission logic ──────────────────────────────────────────

async function applyToJob(page, portal, jobUrl, resumePath) {
  switch (portal) {
    case 'linkedin':  return applyLinkedIn(page, jobUrl, resumePath);
    case 'naukri':    return applyNaukri(page, jobUrl, resumePath);
    case 'indeed':    return applyIndeed(page, jobUrl, resumePath);
    default:
      throw new Error(`Unsupported portal: ${portal}`);
  }
}

async function applyLinkedIn(page, jobUrl, resumePath) {
  await page.goto(jobUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await randomDelay(2000, 4000);

  // Verify still logged in (cookie injection should handle this)
  if (page.url().includes('login') || page.url().includes('authwall')) {
    throw new Error('CookieExpiredError: LinkedIn session expired. Re-run export-cookies.js');
  }

  const easyApplyBtn = await page.$('.jobs-apply-button--top-card button');
  if (!easyApplyBtn) {
    return { success: false, message: 'No Easy Apply button found — external application' };
  }

  await easyApplyBtn.click();
  await randomDelay(1500, 2500);

  // Handle upload step
  const fileInput = await page.$('input[type="file"]');
  if (fileInput) {
    await fileInput.setInputFiles(resumePath);
    await randomDelay(1000, 1500);
  }

  // Navigate steps until Submit
  let steps = 0;
  while (steps < 8) {
    const captcha = await page.$('[class*="captcha"]');
    if (captcha) {
      return { success: false, message: 'CAPTCHA detected — needs human review' };
    }

    // Check for complex textarea questions (> 2 = flag for human)
    const textareas = await page.$$('textarea');
    if (textareas.length > 2) {
      return { success: false, message: 'Complex form — needs human review' };
    }

    const submitBtn = await page.$('button[aria-label*="Submit"], button[aria-label*="submit"]');
    if (submitBtn) {
      await submitBtn.click();
      await randomDelay(2000, 3000);
      return { success: true, message: 'LinkedIn Easy Apply submitted' };
    }

    const nextBtn = await page.$('button[aria-label*="Continue"], button[aria-label*="Review"], .artdeco-button--primary');
    if (!nextBtn) break;
    await nextBtn.click();
    await randomDelay(1000, 2000);
    steps++;
  }

  return { success: false, message: 'Could not complete application flow' };
}

async function applyNaukri(page, jobUrl, resumePath) {
  await page.goto(jobUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await randomDelay(2000, 3500);

  if (page.url().includes('login')) {
    throw new Error('CookieExpiredError: Naukri session expired. Re-run export-cookies.js');
  }

  const applyBtn = await page.$('button.apply-button, #apply-button, .apply-btn');
  if (!applyBtn) {
    return { success: false, message: 'No apply button found' };
  }

  await applyBtn.click();
  await randomDelay(2000, 3000);

  const uploadInput = await page.$('input[type="file"]');
  if (uploadInput) {
    await uploadInput.setInputFiles(resumePath);
    await randomDelay(1000, 1500);
  }

  const submitBtn = await page.$('button[type="submit"], .submit-btn');
  if (submitBtn) {
    await submitBtn.click();
    await randomDelay(2000, 2500);
    return { success: true, message: 'Naukri Quick Apply submitted' };
  }

  return { success: false, message: 'Could not find submit button' };
}

async function applyIndeed(page, jobUrl, resumePath) {
  await page.goto(jobUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await randomDelay(2000, 4000);

  if (page.url().includes('login') || page.url().includes('auth')) {
    throw new Error('CookieExpiredError: Indeed session expired. Re-run export-cookies.js');
  }

  const applyBtn = await page.$('[data-testid="indeedApplyButton"], .ia-IndeedApplyButton');
  if (!applyBtn) {
    return { success: false, message: 'No Indeed Easy Apply button found' };
  }

  await applyBtn.click();
  await randomDelay(2000, 3000);

  // Indeed opens an iframe for applications
  const frame = page.frames().find(f => f.url().includes('smartapply'));
  const context = frame || page;

  const fileInput = await context.$('input[type="file"]');
  if (fileInput) {
    await fileInput.setInputFiles(resumePath);
    await randomDelay(1000, 1500);
  }

  let steps = 0;
  while (steps < 6) {
    const continueBtn = await context.$('button[data-testid="continue-button"]');
    if (!continueBtn) break;
    const btnText = await continueBtn.innerText();
    if (btnText.toLowerCase().includes('submit')) {
      await continueBtn.click();
      await randomDelay(2000, 3000);
      return { success: true, message: 'Indeed Easy Apply submitted' };
    }
    await continueBtn.click();
    await randomDelay(1000, 2000);
    steps++;
  }

  return { success: false, message: 'Could not complete Indeed application flow' };
}

// ── Cookie helpers ────────────────────────────────────────────────────────────

function loadCookies(encPath, portal) {
  if (!fs.existsSync(encPath)) {
    throw new Error(`Cookie file not found: ${encPath}`);
  }

  const cookieSecret = process.env.COOKIE_SECRET;
  if (!cookieSecret) {
    throw new Error('COOKIE_SECRET environment variable not set');
  }

  const encrypted = JSON.parse(fs.readFileSync(encPath, 'utf8'));

  // Decrypt AES-256-GCM
  const key = crypto.scryptSync(cookieSecret, encrypted.salt, 32);
  const decipher = crypto.createDecipheriv(
    'aes-256-gcm',
    key,
    Buffer.from(encrypted.iv, 'hex')
  );
  decipher.setAuthTag(Buffer.from(encrypted.tag, 'hex'));

  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(encrypted.data, 'hex')),
    decipher.final(),
  ]);

  const allCookies = JSON.parse(decrypted.toString('utf8'));
  const portalCookies = allCookies[portal];

  if (!portalCookies || portalCookies.length === 0) {
    throw new Error(`No cookies for portal: ${portal}`);
  }

  // Check expiry of critical cookies
  const now = Date.now() / 1000;
  const expired = portalCookies.filter(c => c.expires && c.expires > 0 && c.expires < now);
  if (expired.length > 0) {
    throw new Error(`Cookies expired for ${portal} (${expired.length} cookies). Re-run export-cookies.js`);
  }

  return portalCookies;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function randomDelay(minMs, maxMs) {
  const delay = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
  return new Promise(resolve => setTimeout(resolve, delay));
}

// ── Start server ──────────────────────────────────────────────────────────────
const PORT = parseInt(process.env.PORT || '3002', 10);
app.listen(PORT, () => {
  console.log(`[submitter] Running on port ${PORT}`);
  console.log(`[submitter] Health: http://localhost:${PORT}/health`);
});
