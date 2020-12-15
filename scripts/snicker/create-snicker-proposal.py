#!/usr/bin/env python3

description="""A rudimentary implementation of creation of a SNICKER proposal.

**THIS TOOL DOES NOT SCAN FOR CANDIDATE TRANSACTIONS**

It only creates proposals on candidate transactions (individually)
that you have already found.

Input: the user's wallet, mixdepth to source their (1) coin from,
and a hex encoded pre-existing bitcoin transaction (fully signed)
as target.
User chooses the input to source the pubkey from, and the output
to use to create the SNICKER coinjoin. Tx fees are sourced from
the config, and the user specifies interactively the number of sats
to award the receiver (can be negative).

Once the proposal is created, it is uploaded to the servers as per
the `servers` setting in `joinmarket.cfg`, unless the -n option is
specified (see help for options), in which case the proposal is
output to stdout in the same string format: base64proposal,hexpubkey.
"""

import sys
from optparse import OptionParser
from jmbase import BytesProducer, bintohex, jmprint, hextobin, \
     EXIT_ARGERROR, EXIT_FAILURE, EXIT_SUCCESS
import jmbitcoin as btc
from jmclient import (RegtestBitcoinCoreInterface, process_shutdown,
     jm_single, load_program_config, check_regtest, select_one_utxo,
     estimate_tx_fee, SNICKERReceiver, add_base_options, get_wallet_path,
     open_test_wallet_maybe, WalletService, SNICKERClientProtocolFactory,
     start_reactor)
from jmclient.configure import get_log

log = get_log()

def main():
    parser = OptionParser(
        usage=
        'usage: %prog [options] walletname hex-tx input-index output-index net-transfer',
        description=description
    )
    add_base_options(parser)
    parser.add_option('-m',
          '--mixdepth',
          action='store',
          type='int',
          dest='mixdepth',
          help='mixdepth/account to spend from, default=0',
          default=0)
    parser.add_option(
        '-g',
        '--gap-limit',
        action='store',
        type='int',
        dest='gaplimit',
        default = 6,
        help='Only to be used with -w; gap limit for Joinmarket wallet, default 6.'
    )
    parser.add_option(
        '-M',
        '--max-mixdepth',
        action='store',
        type='int',
        dest='maxmixdepth',
        default=5,
        help='Only to be used with -w; number of mixdepths for wallet, default 5.'
    )
    parser.add_option(
        '-n',
        '--no-upload',
        action='store_true',
        dest='no_upload',
        default=False,
        help="if set, we don't upload the new proposal to the servers"
    )
    parser.add_option(
        '-f',
        '--txfee',
        action='store',
        type='int',
        dest='txfee',
        default=-1,
        help='Bitcoin miner tx_fee to use for transaction(s). A number higher '
        'than 1000 is used as "satoshi per KB" tx fee. A number lower than that '
        'uses the dynamic fee estimation of your blockchain provider as '
        'confirmation target. This temporarily overrides the "tx_fees" setting '
        'in your joinmarket.cfg. Works the same way as described in it. Check '
        'it for examples.')
    parser.add_option('-a',
                      '--amtmixdepths',
                      action='store',
                      type='int',
                      dest='amtmixdepths',
                      help='number of mixdepths in wallet, default 5',
                      default=5)
    (options, args) = parser.parse_args()
    load_program_config(config_path=options.datadir)
    if len(args) != 5:
        jmprint("Invalid arguments, see --help")
        sys.exit(EXIT_ARGERROR)
    wallet_name, hextx, input_index, output_index, net_transfer = args
    input_index, output_index, net_transfer = [int(x) for x in [
        input_index, output_index, net_transfer]]
    check_regtest()

    # If tx_fees are set manually by CLI argument, override joinmarket.cfg:
    if int(options.txfee) > 0:
        jm_single().config.set("POLICY", "tx_fees", str(options.txfee))
    max_mix_depth = max([options.mixdepth, options.amtmixdepths - 1])
    wallet_path = get_wallet_path(wallet_name, None)
    wallet = open_test_wallet_maybe(
            wallet_path, wallet_name, max_mix_depth,
            wallet_password_stdin=options.wallet_password_stdin,
            gap_limit=options.gaplimit)
    wallet_service = WalletService(wallet)
    if wallet_service.rpc_error:
        sys.exit(EXIT_FAILURE)
    # in this script, we need the wallet synced before
    # logic processing for some paths, so do it now:
    while not wallet_service.synced:
        wallet_service.sync_wallet(fast=not options.recoversync)
    # the sync call here will now be a no-op:
    wallet_service.startService()

    # now that the wallet is available, we can construct a proposal
    # before encrypting it:
    originating_tx = btc.CMutableTransaction.deserialize(hextobin(hextx))
    txid1 = originating_tx.GetTxid()[::-1]
    # the proposer wallet needs to choose a single utxo, from his selected
    # mixdepth, that is bigger than the output amount of tx1 at the given
    # index.
    fee_est = estimate_tx_fee(2, 3, txtype=wallet_service.get_txtype())
    amt_required = originating_tx.vout[output_index].nValue + fee_est
    
    prop_utxo_dict = wallet_service.select_utxos(options.mixdepth,
                            amt_required,select_fn=select_one_utxo)
    prop_utxo = list(prop_utxo_dict)[0]
    prop_utxo_val = prop_utxo_dict[prop_utxo]
    # get the private key for that utxo
    priv = wallet_service.get_key_from_addr(
        wallet_service.script_to_addr(prop_utxo_val['script']))
    # construct the arguments for the snicker proposal:
    our_input_utxo = btc.CMutableTxOut(prop_utxo_val['value'],
                                       prop_utxo_val['script'])

    change_spk = wallet_service.get_new_script(options.mixdepth, 1)
    their_input = (txid1, output_index)
    # we also need to extract the pubkey of the chosen input from
    # the witness; we vary this depending on our wallet type:
    pubkey, msg = btc.extract_pubkey_from_witness(originating_tx, input_index)
    if not msg:
        jmprint("Failed to extract pubkey from transaction: " + msg, "error")
        sys.exit(EXIT_FAILURE)
    encrypted_proposal = wallet_service.create_snicker_proposal(
            prop_utxo, their_input,
            our_input_utxo,
            originating_tx.vout[output_index],
            net_transfer,
            fee_est,
            priv,
            pubkey.format(),
            prop_utxo_val['script'],
            change_spk,
            version_byte=1) + b"," + bintohex(pubkey.format()).encode('utf-8')

    if options.no_upload:
        jmprint(encrypted_proposal.decode("utf-8"))
        sys.exit(EXIT_SUCCESS)
    nodaemon = jm_single().config.getint("DAEMON", "no_daemon")
    daemon = True if nodaemon == 1 else False
    snicker_client = SNICKERPostingClient([encrypted_proposal])
    servers = jm_single().config.get("SNICKER", "servers").split(",")
    snicker_pf = SNICKERClientProtocolFactory(snicker_client, servers)
    start_reactor(jm_single().config.get("DAEMON", "daemon_host"),
                      jm_single().config.getint("DAEMON", "daemon_port"),
                      None, snickerfactory=snicker_pf,
                      daemon=daemon)

class SNICKERPostingClient(object):
    def __init__(self, proposals, info_callback=None,
                 end_requests_callback=None):
        self.proposals = proposals

        # callback for conveying information messages
        if not info_callback:
            self.info_callback = self.default_info_callback
        else:
            self.info_callback = info_callback

        # callback for action at the end of a set of
        # submissions to servers; by default, this
        # is "one-shot"; we submit to all servers in the
        # config, then shut down the script.
        if not end_requests_callback:
            self.end_requests_callback = \
                self.default_end_requests_callback

    def default_end_requests_callback(self, response):
        process_shutdown()

    def default_info_callback(self, msg):
        jmprint(msg)

    def get_proposals(self):
        return self.proposals

if __name__ == "__main__":
    main()
    jmprint('done', "success")
