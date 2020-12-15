#!/usr/bin/env python3

from optparse import OptionParser
import sys
from jmbase import get_log, jmprint
from jmclient import (jm_single, load_program_config, WalletService,
                      open_test_wallet_maybe, get_wallet_path,
                      check_regtest, add_base_options, start_reactor,
                      SNICKERClientProtocolFactory, SNICKERReceiver)
from jmbase.support import EXIT_ARGERROR

jlog = get_log()

def receive_snicker_main():
    usage = """ Use this script to receive proposals for SNICKER
coinjoins, parse them and then broadcast coinjoins
that fit your criteria. See the SNICKER section of
joinmarket.cfg to set your criteria.
The only argument to this script is the (JM) wallet
file against which to check.
Once all proposals have been parsed, the script will
quit.
Usage: %prog [options] [wallet file]
"""
    parser = OptionParser(usage=usage)
    add_base_options(parser)
    parser.add_option('-g', '--gap-limit', action='store', type="int",
                      dest='gaplimit', default=6,
                      help='gap limit for wallet, default=6')
    parser.add_option('-m', '--mixdepth', action='store', type='int',
                      dest='mixdepth', default=0,
                      help="mixdepth to source coins from")
    parser.add_option('-a',
                      '--amtmixdepths',
                      action='store',
                      type='int',
                      dest='amtmixdepths',
                      help='number of mixdepths in wallet, default 5',
                      default=5)

    (options, args) = parser.parse_args()
    if len(args) < 1:
        parser.error('Needs a wallet file as argument')
        sys.exit(EXIT_ARGERROR)
    wallet_name = args[0]
    load_program_config(config_path=options.datadir)

    check_regtest()

    wallet_path = get_wallet_path(wallet_name, None)
    max_mix_depth = max([options.mixdepth, options.amtmixdepths - 1])
    wallet = open_test_wallet_maybe(
        wallet_path, wallet_name, max_mix_depth,
        wallet_password_stdin=options.wallet_password_stdin,
        gap_limit=options.gaplimit)
    wallet_service = WalletService(wallet)

    while not wallet_service.synced:
        wallet_service.sync_wallet(fast=not options.recoversync)
    wallet_service.startService()

    nodaemon = jm_single().config.getint("DAEMON", "no_daemon")
    daemon = True if nodaemon == 1 else False
    snicker_r = SNICKERReceiver(wallet_service)
    servers = jm_single().config.get("SNICKER", "servers").split(",")
    snicker_pf = SNICKERClientProtocolFactory(snicker_r, servers)
    start_reactor(jm_single().config.get("DAEMON", "daemon_host"),
                  jm_single().config.getint("DAEMON", "daemon_port"),
                  None, snickerfactory=snicker_pf,
                  daemon=daemon)

if __name__ == "__main__":
    receive_snicker_main()
    jmprint('done')
