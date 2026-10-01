const BACKEND =
  'https://app12-nextaura-fit.284w7l87aq94.us-south.codeengine.appdomain.cloud'
const BACKEND_HOST =
  'app12-nextaura-fit.284w7l87aq94.us-south.codeengine.appdomain.cloud'

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json',
      'cache-control': 'no-store',
      'access-control-allow-origin': '*',
    },
  })
}

export default {
  async fetch(request) {
    const incoming = new URL(request.url)

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'access-control-allow-origin': '*',
          'access-control-allow-methods': 'GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS',
          'access-control-allow-headers':
            'Content-Type, Authorization, Upgrade, Connection, Sec-WebSocket-Key, Sec-WebSocket-Version, Sec-WebSocket-Protocol, Sec-WebSocket-Extensions',
        },
      })
    }

    if (incoming.pathname === '/health') {
      return json({
        status: 'ok',
        role: 'app12-ce-proxy',
        app: 'kids-game-dimension-builder',
        origin: BACKEND,
      })
    }

    const target = new URL(incoming.pathname + incoming.search, BACKEND)
    const headers = new Headers(request.headers)
    headers.set('Host', BACKEND_HOST)
    headers.set('X-Forwarded-Host', incoming.host)
    headers.set('X-Forwarded-Proto', incoming.protocol.replace(':', ''))

    // WebSocket upgrade: pass the original request through.
    if ((request.headers.get('Upgrade') || '').toLowerCase() === 'websocket') {
      return fetch(target.toString(), request)
    }

    const init = {
      method: request.method,
      headers,
      redirect: 'manual',
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      init.body = request.body
    }

    const response = await fetch(target.toString(), init)
    const out = new Headers(response.headers)
    out.set('X-Proxied-By', 'nextaura-app12')
    out.set('Permissions-Policy', 'microphone=(), camera=()')
    out.set('X-Content-Type-Options', 'nosniff')
    out.set('Referrer-Policy', 'strict-origin-when-cross-origin')
    out.delete('Server')
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: out,
    })
  },
}
