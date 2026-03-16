#!/usr/bin/env python3
import http.server
import socketserver

# Activer le mode multi-thread pour éviter les blocages
socketserver.TCPServer.allow_reuse_address = True

class FixedHandler(http.server.SimpleHTTPRequestHandler):
    # Types MIME corrects
    extensions_map = {
        '': 'application/octet-stream',
        '.html': 'text/html; charset=utf-8',
        '.htm': 'text/html; charset=utf-8',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.ico': 'image/x-icon',
        '.pdf': 'application/pdf',
        '.md': 'text/plain; charset=utf-8',
        '.txt': 'text/plain; charset=utf-8',
    }

PORT = 8888
with socketserver.TCPServer(("0.0.0.0", PORT), FixedHandler) as httpd:
    print(f"Serving on port {PORT}")
    httpd.serve_forever()
