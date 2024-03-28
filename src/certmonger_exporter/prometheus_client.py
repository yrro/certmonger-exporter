import threading

from prometheus_client.core import REGISTRY


# EPEL 8 has an older prometheus_client which don't return the thread for
# us to join on, so instead we re-implement it here.
def start_httpd_server(port, addr='', registry=REGISTRY):
    """Starts a WSGI server for prometheus metrics as a daemon thread."""
    from prometheus_client.exposition import make_wsgi_app, make_server, ThreadingWSGIServer, _SilentHandler, make_server
    app = make_wsgi_app(registry)
    httpd = make_server(addr, port, app, ThreadingWSGIServer, handler_class=_SilentHandler)
    t = threading.Thread(target=httpd.serve_forever)
    t.daemon = True
    t.start()
    return httpd, t

