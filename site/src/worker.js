// Оригиналы карт лежат в R2 и отдаются по /o/<id>.<ext>; всё остальное — статические файлы.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/o/')) return original(request, env, url.pathname.slice(3));
    return env.ASSETS.fetch(request);
  },
};

async function original(request, env, path) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method Not Allowed', { status: 405, headers: { allow: 'GET, HEAD' } });
  }
  let key;
  try {
    key = decodeURIComponent(path);
  } catch {
    return new Response('Bad Request', { status: 400 });
  }
  let obj;
  try {
    obj = request.method === 'HEAD'
      ? await env.ORIGINALS.head(key)
      : await env.ORIGINALS.get(key, { range: request.headers, onlyIf: request.headers });
  } catch {
    return new Response('Range Not Satisfiable', { status: 416 });     // R2 отклонил диапазон
  }
  if (!obj) return new Response('Not Found', { status: 404 });

  const headers = new Headers();
  obj.writeHttpMetadata(headers);
  headers.set('etag', obj.httpEtag);
  headers.set('accept-ranges', 'bytes');
  headers.set('cache-control', 'public, max-age=31536000, immutable');
  headers.set('content-disposition', `attachment; filename="atlas-${key}"`);
  if (request.method === 'HEAD') {
    headers.set('content-length', obj.size);
    return new Response(null, { headers });
  }
  if (!obj.body) return new Response(null, { status: 304, headers });   // условие If-None-Match не прошло
  if (!request.headers.has('range') || !obj.range) return new Response(obj.body, { headers });

  const offset = obj.range.offset ?? obj.size - obj.range.suffix;
  const length = obj.range.length ?? obj.size - offset;
  const start = /^bytes=(\d+)-/.exec(request.headers.get('range'));
  if (offset >= obj.size || length <= 0 || (start && Number(start[1]) >= obj.size)) {
    return new Response('Range Not Satisfiable', { status: 416, headers: { 'content-range': `bytes */${obj.size}` } });
  }
  headers.set('content-range', `bytes ${offset}-${offset + length - 1}/${obj.size}`);
  return new Response(obj.body, { status: 206, headers });
}
