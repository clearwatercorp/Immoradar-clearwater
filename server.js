const express    = require("express");
const puppeteer  = require("puppeteer");
const path       = require("path");
const app        = express();
const PORT       = process.env.PORT || 3000;

app.use(express.static(path.join(__dirname)));

// Cache simple pour éviter de relancer Chrome à chaque requête
let cache = {};
const CACHE_TTL = 15 * 60 * 1000; // 15 minutes

async function scrapeLeBonCoin(keyword) {
  const cacheKey = keyword;
  if (cache[cacheKey] && Date.now() - cache[cacheKey].ts < CACHE_TTL) {
    console.log(`Cache hit: ${keyword}`);
    return cache[cacheKey].data;
  }

  const url = `https://www.leboncoin.fr/recherche?category=9&regions=12&real_estate_type=1,2&price=400000-800000&text=${encodeURIComponent(keyword)}&sort=time&order=desc`;
  console.log(`Scraping: ${url}`);

  const browser = await puppeteer.launch({
    headless: "new",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--no-first-run",
      "--no-zygote",
      "--single-process",
    ],
  });

  try {
    const page = await browser.newPage();
    await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36");
    await page.setViewport({ width: 1280, height: 800 });

    await page.goto(url, { waitUntil: "networkidle2", timeout: 30000 });

    // Attendre les annonces
    await page.waitForSelector('[data-test-id="ad"]', { timeout: 15000 }).catch(() => {});

    const annonces = await page.evaluate(() => {
      const cards = document.querySelectorAll('[data-test-id="ad"]');
      const results = [];
      cards.forEach(card => {
        try {
          const titleEl  = card.querySelector('[data-test-id="ad-title"]') || card.querySelector("h2") || card.querySelector("p[class*='title']");
          const priceEl  = card.querySelector('[data-test-id="price"]') || card.querySelector("p[class*='price']") || card.querySelector("span[class*='price']");
          const locEl    = card.querySelector('[data-test-id="location"]') || card.querySelector("p[class*='location']");
          const linkEl   = card.querySelector("a");
          const descEl   = card.querySelector("p[class*='desc']") || card.querySelector('[data-test-id="description"]");

          const title = titleEl?.textContent?.trim() || "";
          const price = priceEl?.textContent?.trim() || "";
          const location = locEl?.textContent?.trim() || "";
          const link  = linkEl ? "https://www.leboncoin.fr" + linkEl.getAttribute("href") : "#";
          const desc  = descEl?.textContent?.trim() || "";

          if (title) results.push({ title, price, location, link, desc, date: new Date().toISOString() });
        } catch(e) {}
      });
      return results;
    });

    cache[cacheKey] = { ts: Date.now(), data: annonces };
    return annonces;
  } finally {
    await browser.close();
  }
}

// Route principale : scrape LeBonCoin pour un mot-clé
app.get("/scrape", async (req, res) => {
  const keyword = req.query.keyword || "immeuble";
  try {
    const annonces = await scrapeLeBonCoin(keyword);
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.json({ ok: true, keyword, annonces });
  } catch (e) {
    console.error(e);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Health check
app.get("/health", (req, res) => res.json({ status: "ok" }));

app.listen(PORT, () => console.log(`ImmoRadar proxy démarré sur port ${PORT}`));
