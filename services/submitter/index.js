/**
 * services/submitter/index.js
 * Stealth Playwright job application submitter microservice.
 * POST /submit → fills Easy Apply forms using injected session cookies.
 * Port: 3002
 *
 * Security hardening (per security review):
 *   - HMAC-SHA256 shared-secret validation on every /submit request    [HIGH]
 *   - resume_path restricted to RESUME_BASE_DIR (path traversal fix)   [HIGH]
 *   - Screenshots written to temp files, NOT returned in response body [HIGH]
 *   - scrypt N raised to 65536 (OWASP recommended minimum)             [MEDIUM]
 */

'use strict';

const express = require('express');
const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');

chromium.use(StealthPlugin());

const app = express();
app.use(express.json({ limit: '5mb' }));

// ── Configuration ─────────────────────────────────────────────────────────────
const INTERNAL_TOKEN = process.env.INTERNAL_TOKEN || '';
const RESUME_BASE_DIR = path.resolve(
  process.env.RESUME_BASE_DIR || path.join(os.homedir(), '.config/ashvani-job-bot/resumes')
);
const MIN_TOKEN_LENGTH = 32;

if (INTERNAL_TOKEN.length < MIN_TOKEN_LENGTH) {
  console.error(
    `[submitter] FATAL: INTERNAL_TOKEN must be >= ${MIN_TOKEN_LENGTH} chars. ` +
    "Generate: node -e \"console.log(require('crypto').randomBytes(32).toString('hex'))\""
  );
  process.exit(1);
}

// ── HMAC Auth Middleware ──────────────────────────────────────────────────────
function requireInternalAuth(req, res, next) {
  const signature = req.headers['x-internal-token'];
  const timestampStr = req.headers['x-timestamp'];

  if (!signature || !timestampStr) {
    return res.status(401).json({ success: false, error: 'Missing auth headers' });
  }

  const requestMinute = parseInt(timestampStr, 10);
  const currentMinute = Math.floor(Date.now() / 1000 / 60);

  if (Math.abs(currentMinute - requestMinute) > 1) {
    return res.status(401).json({ success: false, error: 'Timestamp expired — replay attack?' });
  }

  const { portal, job_id } = req.body;
  if (!portal || !job_id) return next(); // let field validation handle it

  const message = `${timestampStr}:${portal}:${job_id}`;
  const expected = crypto.createHmac('sha256', INTERNAL_TOKEN).update(message).digest('hex');

  // Use constant-time comparison to prevent timing attacks
  const sigBuf = Buffer.from(signature.toLowerCase().padEnd(expected.length, '0').slice(0, expected.length), 'hex');
  const expBuf = Buffer.from(expected, 'hex');

  if (sigBuf.length !== expBuf.length || !crypto.timingSafeEqual(sigBuf, expBuf)) {
    console.warn(`[submitter] Auth failed: portal=${portal} job=${job_id}`);
    return res.status(401).json({ success: false, error: 'Invalid X-Internal-Token' });
  }

  next();
}

// ── Path Traversal Guard ──────────────────────────────────────────────────────
function validateResumePath(filePath, baseDir) {
  const resolved = path.resolve(filePath);
  const base = path.resolve(baseDir);

  if (!resolved.startsWith(base + path.sep) && resolved !== base) {
    throw new Error(`Path traversal blocked: '${filePath}' is outside allowed dir '${baseDir}'`);
  }
  if (!fs.existsSync(resolved)) {
    throw new Error(`Resume file not found: ${resolved}`);
  }
  return resolved;
}

// ── Screenshot Helper ─────────────────────────────────────────────────────────
async function saveScreenshot(page, prefix = 'screenshot') {
  try {
    const tmpFile = path.join(os.tmpdir(), `ashvani-${prefix}-${Date.now()}.png`);
    await page.screenshot({ path: tmpFile, fullPage: false });
    return tmpFile;
  } catch (_) {
    return null;
  }
}

// ── Health check ──────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'submitter', port: process.env.PORT || 3002 });
});

// ── POST /submit ──────────────────────────────────────────────────────────────
app.post('/submit', requireInternalAuth, async (req, res) => {
  const { portal, job_url, job_id, company, role, resume_path, cookie_file } = req.body;

  if (!portal || !job_url || !resume_path || !job_id) {
    return res.status(400).json({ success: false, error: 'Missing required fields: portal, job_url, job_id, resume_path' });
  }

  // Path traversal prevention
  let safePath;
  try {
    safePath = validateResumePath(resume_path, RESUME_BASE_DIR);
  } catch (err) {
    console.error(`[submitter] Path validation: ${err.message}`);
    return res.status(400).json({ success: false, error: `Invalid resume_path: ${err.message}` });
  }

  const cookiePath = cookie_file || path.resolve(
    process.env.HOME || os.homedir(), '.config/ashvani-job-bot/cookies.enc'
  );

  let cookies;
  try {
    cookies = loadCookies(cookiePath, portal);
  } catch (err) {
    return res.status(401).json({
      success: false,
      error: 'CookieExpiredError',
      message: `Cookies missing/expired for ${portal}. Run: node tools/export-cookies.js`,
    });
  }

  console.log(`[submitter] Starting ${portal} for ${company} | ${role}`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage', '--no-sandbox', '--disable-setuid-sandbox'],
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    locale: 'en-IN',
    timezoneId: 'Asia/Kolkata',
  });

  await context.addCookies(cookies);
  const page = await context.newPage();

  try {
    const result = await applyToJob(page, portal, job_url, safePath);
    // Screenshot to temp file ONLY — no base64 in response
    const screenshotPath = await saveScreenshot(page, `${portal}-${job_id}`);
    await browser.close();

    console.log(`[submitter] ${result.success ? '✓' : '✗'} ${company} — ${result.message}`);

    return res.json({
      success: result.success,
      application_id: result.application_id || `${portal}-${job_id}-${Date.now()}`,
      screenshot_path: screenshotPath,
      message: result.message,
    });

  } catch (err) {
    console.error(`[submitter] Error for job ${job_id}:`, err.message);
    const screenshotPath = await saveScreenshot(page, `error-${job_id}`);
    await browser.close();

    return res.status(500).json({
      success: false,
      error: err.message,
      screenshot_path: screenshotPath,
      message: `Application failed: ${err.message}`,
    });
  }
});

// ── Portal Logic ──────────────────────────────────────────────────────────────

async function applyToJob(page, portal, jobUrl, resumePath) {
  switch (portal) {
    case 'linkedin': return applyLinkedIn(page, jobUrl, resumePath);
    case 'naukri':   return applyNaukri(page, jobUrl, resumePath);
    case 'indeed':   return applyIndeed(page, jobUrl, resumePath);
    default:         throw new Error(`Unsupported portal: ${portal}`);
  }
}

async function applyLinkedIn(page, jobUrl, resumePath) {
  await page.goto(jobUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await randomDelay(2000, 4000);

  if (page.url().includes('login') || page.url().includes('authwall')) {
    throw new Error('CookieExpiredError: LinkedIn session expired. Re-run export-cookies.js');
  }

  const easyApplyBtn = await page.$('.jobs-apply-button--top-card button');
  if (!easyApplyBtn) return { success: false, message: 'No Easy Apply button — external application' };

  await easyApplyBtn.click();
  await randomDelay(1500, 2500);

  const fileInput = await page.$('input[type="file"]');
  if (fileInput) { await fileInput.setInputFiles(resumePath); await randomDelay(1000, 1500); }

  let steps = 0;
  while (steps < 8) {
    if (await page.$('[class*="captcha"]')) return { success: false, message: 'CAPTCHA — needs human review' };
    if ((await page.$$('textarea')).length > 2) return { success: false, message: 'Complex form — needs human review' };

    const submitBtn = await page.$('button[aria-label*="Submit"], button[aria-label*="submit"]');
    if (submitBtn) { await submitBtn.click(); await randomDelay(2000, 3000); return { success: true, message: 'LinkedIn Easy Apply submitted' }; }

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

  if (page.url().includes('login')) throw new Error('CookieExpiredError: Naukri session expired.');

  const applyBtn = await page.$('button.apply-button, #apply-button, .apply-btn');
  if (!applyBtn) return { success: false, message: 'No apply button found' };

  await applyBtn.click(); await randomDelay(2000, 3000);

  const uploadInput = await page.$('input[type="file"]');
  if (uploadInput) { await uploadInput.setInputFiles(resumePath); await randomDelay(1000, 1500); }

  const submitBtn = await page.$('button[type="submit"], .submit-btn');
  if (submitBtn) { await submitBtn.click(); await randomDelay(2000, 2500); return { success: true, message: 'Naukri Quick Apply submitted' }; }

  return { success: false, message: 'Could not find submit button' };
}

async function applyIndeed(page, jobUrl, resumePath) {
  await page.goto(jobUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await randomDelay(2000, 4000);

  if (page.url().includes('login') || page.url().includes('auth')) throw new Error('CookieExpiredError: Indeed session expired.');

  const applyBtn = await page.$('[data-testid="indeedApplyButton"], .ia-IndeedApplyButton');
  if (!applyBtn) return { success: false, message: 'No Indeed Easy Apply button found' };

  await applyBtn.click(); await randomDelay(2000, 3000);

  const frame = page.frames().find(f => f.url().includes('smartapply'));
  const ctx = frame || page;

  const fileInput = await ctx.$('input[type="file"]');
  if (fileInput) { await fileInput.setInputFiles(resumePath); await randomDelay(1000, 1500); }

  let steps = 0;
  while (steps < 6) {
    const continueBtn = await ctx.$('button[data-testid="continue-button"]');
    if (!continueBtn) break;
    if ((await continueBtn.innerText()).toLowerCase().includes('submit')) {
      await continueBtn.click(); await randomDelay(2000, 3000);
      return { success: true, message: 'Indeed Easy Apply submitted' };
    }
    await continueBtn.click(); await randomDelay(1000, 2000);
    steps++;
  }
  return { success: false, message: 'Could not complete Indeed application flow' };
}

// ── Cookie Decryption ─────────────────────────────────────────────────────────

function loadCookies(encPath, portal) {
  if (!fs.existsSync(encPath)) throw new Error(`Cookie file not found: ${encPath}`);

  const cookieSecret = process.env.COOKIE_SECRET;
  if (!cookieSecret) throw new Error('COOKIE_SECRET not set');

  const encrypted = JSON.parse(fs.readFileSync(encPath, 'utf8'));

  // scrypt N=65536 — matches updated Python session_manager.py
  const key = crypto.scryptSync(cookieSecret, encrypted.salt, 32, { N: 65536 });
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(encrypted.iv, 'hex'));
  decipher.setAuthTag(Buffer.from(encrypted.tag, 'hex'));

  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(encrypted.data, 'hex')),
    decipher.final(),
  ]);

  const allCookies = JSON.parse(decrypted.toString('utf8'));
  const portalCookies = allCookies[portal];
  if (!portalCookies || portalCookies.length === 0) throw new Error(`No cookies for portal: ${portal}`);

  const now = Date.now() / 1000;
  const expired = portalCookies.filter(c => c.expires && c.expires > 0 && c.expires < now);
  if (expired.length > 0) throw new Error(`${expired.length} cookie(s) expired for ${portal}. Re-run export-cookies.js`);

  return portalCookies;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function randomDelay(minMs, maxMs) {
  return new Promise(resolve => setTimeout(resolve, Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs));
}

// ── Start (bind to 127.0.0.1 — localhost only) ────────────────────────────────
const PORT = parseInt(process.env.PORT || '3002', 10);
app.listen(PORT, '127.0.0.1', () => {
  console.log(`[submitter] 127.0.0.1:${PORT} | resume base: ${RESUME_BASE_DIR}`);
});
