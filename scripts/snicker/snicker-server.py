#!/usr/bin/env python3

"""
A rudimentary implementation of a server, allowing POST of proposals
in base64 format, and GET of all current proposals, for SNICKER.
Serves only over Tor hidden service.
"""

from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.internet.endpoints import TCP4ClientEndpoint, UNIXClientEndpoint
import txtorcon
import sys
import base64
import json
from io import BytesIO
from jmbase import jmprint, hextobin
from jmclient import process_shutdown, jm_single, load_program_config
from jmclient.configure import get_log

log = get_log()

class SNICKERServer(Resource):
    # rudimentary: flat file, TODO location of file
    DATABASE = "snicker-proposals.txt"

    def __init__(self):
        super().__init__()

    isLeaf = True

    def return_error(self, request, error_meaning,
                    error_code="unavailable", http_code=400):
        """
        We return, to the sender, stringified json in the body as per the above.
        """
        request.setResponseCode(http_code)
        request.setHeader(b"content-type", b"text/html; charset=utf-8")
        log.debug("Returning an error: " + str(
            error_code) + ": " + str(error_meaning))
        return json.dumps({"errorCode": error_code,
                           "message": error_meaning}).encode("utf-8")

    def render_GET(self, request):
        """ Simplest possible: any GET request retrieves the entire current data set.
        """
        proposals = self.get_all_current_proposals()
        request.setHeader(b"content-length", ("%d" % len(proposals)).encode("ascii"))
        return proposals.encode("ascii")

    def render_POST(self, request):
        """ An individual proposal may be submitted in base64, with key
        appended after newline separator in hex.
        """
        log.debug("The server got this POST request: ")
        # unfortunately the twisted Request object is not
        # easily serialized:
        log.debug(request)
        log.debug(request.method)
        log.debug(request.uri)
        log.debug(request.args)
        sender_parameters = request.args
        log.debug(request.path)
        # defer logging of raw request content:
        proposals = request.content
        if not isinstance(proposals, BytesIO):
            return self.return_error(request, "Invalid request format",
                                         "invalid-request-format")
        proposals = proposals.read()
        # for now, only allowing proposals of form "base64ciphertext,hexkey",
        #newline separated:
        proposals = proposals.split(b"\n")
        log.debug("Client send proposal list of length: " + str(
            len(proposals)))
        accepted_proposals = []
        for proposal in proposals:
            if len(proposal) == 0:
                continue
            try:
                encryptedtx, key = proposal.split(b",")
                bin_key = hextobin(key.decode('utf-8'))
                base64.b64decode(encryptedtx)
            except:
                log.warn("This proposal was not accepted: " + proposal.decode(
                    "utf-8"))
                # give up immediately in case of format error:
                return self.return_error(request, "Invalid request format",
                                         "invalid-request-format")
            accepted_proposals.append(proposal)

        # the proposals are valid format-wise; add them to the database
        for p in accepted_proposals:
            self.add_proposal(p.decode("utf-8"))
        content = "proposals-accepted"
        request.setHeader(b"content-length", ("%d" % len(content)).encode("ascii"))
        return content.encode("ascii")

    def add_proposal(self, p):
        with open(self.DATABASE, "a") as f:
            f.write(p + "\n")

    def get_all_current_proposals(self):
        with open(self.DATABASE, "r") as f:
            proposals = f.read()
        return proposals

class SNICKERServerManager(object):

    def __init__(self, port, uri_created_callback=None,
                 info_callback=None,
                 shutdown_callback=None):
        self.port = port
        if not uri_created_callback:
            self.uri_created_callback = self.default_info_callback
        else:
            self.uri_created_callback = uri_created_callback
        if not info_callback:
            self.info_callback = self.default_info_callback
        else:
            self.info_callback = info_callback

        self.shutdown_callback =shutdown_callback

    def default_info_callback(self, msg):
        jmprint(msg)

    def start_snicker_server_and_tor(self):
        """ Packages the startup of the receiver side.
        """
        self.server = SNICKERServer()
        self.site = Site(self.server)
        self.site.displayTracebacks = False
        jmprint("Attempting to start onion service on port: " + str(
            self.port) + " ...")
        self.start_tor()

    def setup_failed(self, arg):
        errmsg = "Setup failed: " + str(arg)
        log.error(errmsg)
        self.info_callback(errmsg)
        process_shutdown()

    def create_onion_ep(self, t):
        self.tor_connection = t
        return t.create_onion_endpoint(self.port, version=3)

    def onion_listen(self, onion_ep):
        return onion_ep.listen(self.site)

    def print_host(self, ep):
        """ Callback fired once the HS is available;
        receiver user needs a BIP21 URI to pass to
        the sender:
        """
        self.info_callback("Your hidden service is available: ")
        # Note that ep,getHost().onion_port must return the same
        # port as we chose in self.port; if not there is an error.
        assert ep.getHost().onion_port == self.port
        self.uri_created_callback(str(ep.getHost().onion_uri))

    def start_tor(self):
        """ This function executes the workflow
        of starting the hidden service.
        """
        control_host = jm_single().config.get("PAYJOIN", "tor_control_host")
        control_port = int(jm_single().config.get("PAYJOIN", "tor_control_port"))
        if str(control_host).startswith('unix:'):
            control_endpoint = UNIXClientEndpoint(reactor, control_host[5:])
        else:
            control_endpoint = TCP4ClientEndpoint(reactor, control_host, control_port)
        d = txtorcon.connect(reactor, control_endpoint)
        d.addCallback(self.create_onion_ep)
        d.addErrback(self.setup_failed)
        # TODO: add errbacks to the next two calls in
        # the chain:
        d.addCallback(self.onion_listen)
        d.addCallback(self.print_host)

    def shutdown(self):
        self.tor_connection.protocol.transport.loseConnection()
        process_shutdown(self.mode)
        self.info_callback("Hidden service shutdown complete")
        if self.shutdown_callback:
            self.shutdown_callback()

def snicker_server_start(port):
    ssm = SNICKERServerManager(port)
    ssm.start_snicker_server_and_tor()

if __name__ == "__main__":
    load_program_config(bs="no-blockchain")
    if len(sys.argv) < 2:
        port = 80
    else:
        port = int(sys.argv[1])
    snicker_server_start(port)
    reactor.run()