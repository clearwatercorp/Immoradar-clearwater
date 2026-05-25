const express = require("express");
const fetch   = require("node-fetch");
const app     = express();
const PORT    = process.env.PORT || 3000;

// Servir le dashboard HTML
app.use(express.static("public"));

// Proxy RSS — appelé par le dashboard
app.get("/rss", async (req, res) => {
  const url = req.query.url;
  if (!url) return res.status(400).json({ error: "Paramètre url manquant" });
  try {
    const response = await fetch(decodeURIComponent(url), {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
      },
      timeout: 10000,
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const xml = await response.text();
    res.setHeader("Content-Type", "application/xml");
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.send(xml);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.listen(PORT, () => console.log(`ImmoRadar proxy démarré sur port ${PORT}`));
