"""
Invoke::

    soapbox_daemon path_to_daemon.ini

"""

import sys
import logging
import logging.config
import json
import sqlite3
from typing import Type

from configparser import ConfigParser
from http.server import HTTPServer, BaseHTTPRequestHandler

_log = logging.getLogger(__name__)


class MetadataDB(object):
    """
    A context manager providing an SQLite connection to the ``metadata_log`` DB.
    It commits and closes the DB when exiting the context.

    Parameters:
        conf: as provided by ``ConfigParser``
    """
    def __init__(self, config:Type[ConfigParser]):
        self._connection = sqlite3.connect(config['metadata_log']['db'])

    def __enter__(self) -> Type[sqlite3.Connection]:
        return self._connection

    def __exit__(self, type, value, traceback):
        self._connection.commit()
        self._connection.close()


def get_config() -> ConfigParser:
    """
    Parses ``sys.argv`` to find the config file's path.
    Does some basic configuration, and return a loaded ``ConfigParser``.
    """
    if len(sys.argv) < 2:
        print("Missing argument: path to daemon.ini", file=sys.stderr)
        sys.exit(1)
    conf = ConfigParser()
    conf.read(sys.argv[1])
    logging.config.fileConfig(sys.argv[1], disable_existing_loggers=False)
    return conf


# TODO decorator to try/except Exception and send_reponse_only 500

class SoapboxHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('content-length'))
        data = json.loads(self.rfile.read(length))
        self.rfile.close()
        _log.debug("POST %s got %r", self.path, data)

        self.send_response(200)
        self.end_headers()
    
    def log_message(self, *args):
        _log.info(*args)


class SoapboxServer(HTTPServer):
    allow_reuse_address = True

    def server_activate(self):
        _log.info("SoapboxServer listening %r", self.server_address)
        super().server_activate()


def main():
    conf = get_config()
    server_conf = (conf['listen']['address'], int(conf['listen']['port']))
    with SoapboxServer(server_conf, SoapboxHandler) as server:
        server.serve_forever()
