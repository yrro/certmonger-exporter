import threading

from prometheus_client.core import REGISTRY


# EL8's Python 3.6 maxes out at prometheus-client 0.17, which doesn't return
# the thread/server objects. Re-implement here.
def start_http_server(port, addr='', registry=REGISTRY):
    """Starts a WSGI server for prometheus metrics as a daemon thread."""
    from prometheus_client.exposition import make_wsgi_app, make_server, ThreadingWSGIServer, _SilentHandler, make_server
    app = make_wsgi_app(registry)
    httpd = make_server(addr, port, app, ThreadingWSGIServer, handler_class=_SilentHandler)
    t = threading.Thread(target=httpd.serve_forever)
    t.daemon = True
    t.start()
    return httpd, t

