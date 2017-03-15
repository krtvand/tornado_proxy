import json
import logging
import os
import sys
import socket
from urllib.parse import urlparse, urlunparse

import tornado.httpserver
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.httpclient
import tornado.httputil


MAP = {
    '127.0.0.1:77': {x for x in range(7700, 7799)},
    '127.0.0.1:78': {x for x in range(7800, 7899)}
}
DEFAULT_DESTINATION = '127.0.0.1:77'


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(u'%(levelname)-8s [%(asctime)s]  %(message)s')
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


__all__ = ['ProxyHandler', 'run_proxy']

class ProxyException(Exception):
    pass


def fetch_request(client_request, callback, **kwargs):
    client = tornado.httpclient.AsyncHTTPClient()
    client.fetch(client_request, callback, raise_error=False)


class ProxyHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'POST']

    def compute_etag(self):
        return None  # disable tornado Etag

    def get_field_from_json_body(self, body, field_name):
        body_obj = json.loads(body.decode('utf-8'))
        if field_name in body_obj:
            return body_obj[field_name]
        else:
            raise ProxyException(
                '{} field not found in requests json body'.format(field_name))

    def find_dest_host_by_term_id(self, terminal_id):
        for dest in MAP:
            if terminal_id in MAP[dest]:
                destination = dest
                break
        else:
            destination = DEFAULT_DESTINATION
        return destination

    def get_dest_host(self, server_request):
        if 'content-type' in server_request.headers:
            if server_request.headers['content-type'] == 'application/json':
                terminal_id = self.get_field_from_json_body(server_request.body, 'terminal_id')
                return self.find_dest_host_by_term_id(terminal_id)
            else:
                raise ProxyException('Content-type should be application/json')
        else:
            raise ProxyException('Content-type header not found')

    def make_client_request(self, server_request):
        kwargs = {}
        dest_host = self.get_dest_host(server_request)
        url = urlunparse(
            [server_request.protocol, dest_host,
             server_request.path, server_request.query,
             None, None]
        )
        kwargs['method'] = server_request.method
        kwargs['headers'] = server_request.headers
        if server_request.body:
            kwargs['body'] = server_request.body
        else:
            kwargs['body'] = None

        client_req = tornado.httpclient.HTTPRequest(url, **kwargs)
        return client_req

    @tornado.web.asynchronous
    def get(self):
        logger.debug('Handle %s request to %s', self.request.method,
                     self.request.uri)

        def handle_response(response):
            if (response.error and not
            isinstance(response.error, tornado.httpclient.HTTPError)):
                self.set_status(500)
                self.write('Internal server error:\n' + str(response.error))
            else:
                self.set_status(response.code, response.reason)
                self._headers = tornado.httputil.HTTPHeaders()  # clear tornado default header

                for header, v in response.headers.get_all():
                    if header not in ('Content-Length', 'Transfer-Encoding', 'Content-Encoding', 'Connection'):
                        self.add_header(header, v)  # some header appear multiple times, eg 'Set-Cookie'

                if response.body:
                    self.set_header('Content-Length', len(response.body))
                    self.write(response.body)
            self.finish()

        try:
            client_request = self.make_client_request(self.request)
            fetch_request(client_request, handle_response)
        except (tornado.httpclient.HTTPError, ProxyException) as e:
            if hasattr(e, 'response') and e.response:
                handle_response(e.response)
            else:
                self.set_status(500)
                self.write('Internal server error:\n' + str(e))
                self.finish()

    @tornado.web.asynchronous
    def post(self):
        return self.get()

def run_proxy(port, start_ioloop=True):
    """
    Run proxy on the specified port. If start_ioloop is True (default),
    the tornado IOLoop will be started immediately.
    """
    app = tornado.web.Application([
        (r'.*', ProxyHandler),
    ])
    app.listen(port)
    ioloop = tornado.ioloop.IOLoop.instance()
    if start_ioloop:
        ioloop.start()


if __name__ == '__main__':
    port = 88

    print("Starting HTTP proxy on port %d" % port)
    run_proxy(port)