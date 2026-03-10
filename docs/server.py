#!/usr/bin/env python3
import http.server
import socketserver

class UTF8Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

PORT = 8888
with socketserver.TCPServer(("0.0.0.0", PORT), UTF8Handler) as httpd:
    print(f"Serving on port {PORT}")
    httpd.serve_forever()
