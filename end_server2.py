import time

import tornado.ioloop
import tornado.web

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        # time.sleep(2)
        self.write("Hello, world")
    def post(self):
        self.write("Hello, world")

if __name__ == "__main__":
    application = tornado.web.Application([
        (r"/", MainHandler),
    ])
    application.listen(77)
    tornado.ioloop.IOLoop.current().start()