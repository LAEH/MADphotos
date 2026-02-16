#!/usr/bin/env node
/**
 * Capture screenshots of MADphotos ISIT view on different devices
 * Saves to frontend/system/public/screenshots/devices/
 */

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const DEVICES = [
  // Laptops
  { name: 'macbook-pro-16', width: 1728, height: 1117, type: 'laptop' },
  { name: 'macbook-air-13', width: 1440, height: 900, type: 'laptop' },

  // Tablets - portrait
  { name: 'ipad-pro-12-portrait', width: 1024, height: 1366, type: 'tablet' },
  { name: 'ipad-air-11-portrait', width: 820, height: 1180, type: 'tablet' },
  { name: 'ipad-mini-portrait', width: 744, height: 1133, type: 'tablet' },

  // Tablets - landscape
  { name: 'ipad-10-landscape', width: 1080, height: 810, type: 'tablet' },
  { name: 'ipad-mini-landscape', width: 1133, height: 744, type: 'tablet' },

  // Mobile - portrait
  { name: 'iphone-17-pro-max', width: 440, height: 956, type: 'mobile' },
  { name: 'iphone-15-pro', width: 393, height: 852, type: 'mobile' },
  { name: 'iphone-se', width: 375, height: 667, type: 'mobile' },
  { name: 'pixel-8-pro', width: 412, height: 915, type: 'mobile' },
];

const CHROME_HEIGHTS = {
  laptop: 120,
  tablet: 94,
  mobile: 104,
};

const OUTPUT_DIR = path.join(__dirname, '../frontend/system/public/screenshots/devices');
const URL = 'http://localhost:3000/#isit';

async function captureScreenshots() {
  console.log('🚀 Launching browser...');
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  // Create output directory
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  console.log(`📸 Capturing screenshots for ${DEVICES.length} devices...\n`);

  for (const device of DEVICES) {
    const page = await browser.newPage();

    // Calculate viewport (screen minus browser chrome)
    const chromeHeight = CHROME_HEIGHTS[device.type];
    const viewportHeight = device.height - chromeHeight;

    // Set viewport
    await page.setViewport({
      width: device.width,
      height: viewportHeight,
      deviceScaleFactor: 1,
    });

    console.log(`📱 ${device.name}: ${device.width}×${viewportHeight} (chrome: ${chromeHeight}px)`);

    try {
      // Navigate to ISIT view
      await page.goto(URL, {
        waitUntil: 'networkidle2',
        timeout: 30000
      });

      // Wait for images to load
      await page.waitForSelector('.isit-card', { timeout: 10000 });
      await new Promise(resolve => setTimeout(resolve, 2000)); // Extra time for images

      // Capture screenshot
      const outputPath = path.join(OUTPUT_DIR, `${device.name}.png`);
      await page.screenshot({
        path: outputPath,
        type: 'png'
      });

      console.log(`   ✅ Saved: ${device.name}.png`);
    } catch (error) {
      console.error(`   ❌ Failed: ${device.name} - ${error.message}`);
    }

    await page.close();
  }

  await browser.close();
  console.log('\n✨ Done! Screenshots saved to:', OUTPUT_DIR);
}

// Run
captureScreenshots().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
