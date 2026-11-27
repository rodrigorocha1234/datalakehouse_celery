import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
     generate_latest,
    multiprocess,
)


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/metrics", "/"):
            multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
            if multiproc_dir and os.path.isdir(multiproc_dir):
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)
                data = generate_latest(registry)
            else:
                data = generate_latest()

            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/health":
            body = b'{"status":"healthy"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def main():
    port = int(os.getenv("PORT", "8000"))
    multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus")
    os.makedirs(multiproc_dir, exist_ok=True)
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    print(f"Servidor de métricas Prometheus iniciado na porta {port}...")
    server.serve_forever()


if __name__ == "__main__":
    main()

