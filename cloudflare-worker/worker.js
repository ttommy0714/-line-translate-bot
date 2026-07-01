export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(wakeRender());
  },

  async fetch(request, env, ctx) {
    const result = await wakeRender();
    return new Response(JSON.stringify(result, null, 2), {
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  },
};

async function wakeRender() {
  const targets = [
    "https://line-translate-bot-wvbq.onrender.com/health",
    "https://line-translate-bot-wvbq.onrender.com/test-translate?q=%E4%BD%A0%E5%A5%BD&to=id",
  ];

  const results = [];

  for (const url of targets) {
    try {
      const startedAt = Date.now();
      const response = await fetch(url, {
        method: "GET",
        cf: { cacheTtl: 0, cacheEverything: false },
      });
      const body = await response.text();

      results.push({
        url,
        ok: response.ok,
        status: response.status,
        duration_ms: Date.now() - startedAt,
        body: body.slice(0, 300),
      });
    } catch (error) {
      results.push({
        url,
        ok: false,
        error: String(error),
      });
    }
  }

  return {
    service: "line-translate-bot-wvbq keepalive",
    checked_at: new Date().toISOString(),
    results,
  };
}
