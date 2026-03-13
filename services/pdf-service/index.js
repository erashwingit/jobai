/**
 * services/pdf-service/index.js
 * Puppeteer-based PDF generation microservice.
 * POST /generate-pdf  → accepts JSON resume data, returns PDF bytes.
 * Port: 3001
 */

'use strict';

const express = require('express');
const puppeteer = require('puppeteer');
const nunjucks = require('nunjucks');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json({ limit: '2mb' }));

// ── Nunjucks template engine (Jinja2-compatible) ──────────────────────────────
// Templates resolved from ../../templates/ relative to this file
const TEMPLATE_DIR = path.resolve(__dirname, '../../templates');
nunjucks.configure(TEMPLATE_DIR, { autoescape: true });

// ── Health check ─────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'pdf-service', port: 3001 });
});

// ── POST /generate-pdf ────────────────────────────────────────────────────────
/**
 * Request body (JSON):
 * {
 *   "cv": { ...resume YAML data... },
 *   "design": { "color": "#004f90", ... },
 *   "generated_date": "2026-03-13"
 * }
 *
 * Response: application/pdf bytes
 */
app.post('/generate-pdf', async (req, res) => {
  const startTime = Date.now();

  try {
    const { cv, design, generated_date } = req.body;

    if (!cv || !cv.name) {
      return res.status(400).json({ error: 'Missing required field: cv.name' });
    }

    // Render HTML via Nunjucks (Jinja2-compatible)
    const html = nunjucks.render('resume.html', {
      cv,
      design: design || { color: '#004f90' },
      generated_date: generated_date || new Date().toISOString().slice(0, 10),
    });

    // Launch Puppeteer and generate PDF
    const browser = await puppeteer.launch({
      headless: 'new',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--font-render-hinting=none',
      ],
    });

    const page = await browser.newPage();

    // Set content and wait for fonts/images to load
    await page.setContent(html, { waitUntil: 'networkidle0' });

    const pdfBuffer = await page.pdf({
      format: 'A4',
      printBackground: true,
      margin: { top: '2cm', bottom: '2cm', left: '2cm', right: '2cm' },
    });

    await browser.close();

    const elapsed = Date.now() - startTime;
    console.log(`[pdf-service] PDF generated in ${elapsed}ms for: ${cv.name}`);

    res.set({
      'Content-Type': 'application/pdf',
      'Content-Disposition': `attachment; filename="${sanitizeFilename(cv.name)}-resume.pdf"`,
      'Content-Length': pdfBuffer.length,
      'X-Generation-Time-Ms': elapsed,
    });
    res.send(pdfBuffer);

  } catch (err) {
    console.error('[pdf-service] Error generating PDF:', err.message);
    res.status(500).json({ error: 'PDF generation failed', details: err.message });
  }
});

// ── POST /render-html ─────────────────────────────────────────────────────────
// Debug endpoint: returns rendered HTML (useful for template testing)
app.post('/render-html', (req, res) => {
  try {
    const { cv, design, generated_date } = req.body;
    const html = nunjucks.render('resume.html', {
      cv,
      design: design || { color: '#004f90' },
      generated_date: generated_date || new Date().toISOString().slice(0, 10),
    });
    res.set('Content-Type', 'text/html');
    res.send(html);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function sanitizeFilename(name) {
  return name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-').slice(0, 60);
}

// ── Start server ──────────────────────────────────────────────────────────────
const PORT = parseInt(process.env.PORT || '3001', 10);
app.listen(PORT, () => {
  console.log(`[pdf-service] Running on port ${PORT}`);
  console.log(`[pdf-service] Template directory: ${TEMPLATE_DIR}`);
  console.log(`[pdf-service] Health: http://localhost:${PORT}/health`);
});
