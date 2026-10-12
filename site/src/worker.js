// Оригиналы карт лежат в R2 и отдаются по /o/<id>.<ext>; всё остальное — статические файлы.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/o/')) {
      if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('Method Not Allowed', { status: 405 });
      const key = decodeURIComponent(url.pathname.slice(3));
      const obj = await env.ORIGINALS.get(key);
      if (!obj) return new Response('Not Found', { status: 404 });
      const headers = new Headers();
      obj.writeHttpMetadata(headers);
      headers.set('etag', obj.httpEtag);
      headers.set('cache-control', 'public, max-age=31536000, immutable');
      headers.set('content-disposition', `attachment; filename="atlas-${key}"`);
      return new Response(request.method === 'HEAD' ? null : obj.body, { headers });
    }
    return env.ASSETS.fetch(request);
  },
};
