## INSTRUCTIONS FOR TESTERS of SNICKER

Current pull request/branch [here](https://github.com/JoinMarket-Org/joinmarket-clientserver/pull/768).

Instructions here are very subject to change. This was written from commit https://github.com/JoinMarket-Org/joinmarket-clientserver/pull/768/commits/b545986cb5df1798dc71b91cdaa2a917638bbd5c

#### Quick review of SNICKER functionality

For formal specs as currently implemented, please use [this](https://gist.github.com/AdamISZ/2c13fb5819bd469ca318156e2cf25d79)

Essentially, this is a two party but non-interactive protocol. The **proposer** will identify a candidate transaction where he has some confidence that one or more inputs are owned by the same party as one output, and that that party has SNICKER receiver functionality.
Given those conditions, he'll create one or more **proposals** which are of form `base64-encoded-ECIES-encrypted-PSBT,hex-encoded-pubkey` (the separator is literally a comma; this is ASCII encoded), and send them to a **snicker-server** which is hosted at an onion address (possibly TLS but let's stick with onion for now, it's easier). (They could also be sent manually.)
The **snicker-server** just hosts the proposals and lets others read them. For the purpose of testing it's fine that we don't have a good implementation of this, just a bare-bones version that stores them in a file and lets others access.
The **receiver** then polls this server (for testing, make the polling loop fast; in real usage it should be slow), reads all the existing proposals using a `GET` request with no arguments, and if it can decrypt and sanity check the transaction OK, it co-signs it and broadcasts it. Note: *the receiver wallet will store its new coins output from the coinjoin, as imported keys; they are not part of the HD tree, although derivable from history*.

#### Choice of network

**Regtest** is strongly recommended if you are interested in testing functionality quickly, on your own. See [here](TESTING.md) for some info on regtest setup.

**Testnet** will be helpful especially if you intend to test with others. This can be done by simply sharing proposals or sharing proposal server locations as onion addresses, and possibly communicating with other testers to identify candidate transactions (obviously this strays far from the intended way SNICKER will be used, but it might be convenient to test workflow).

Mainnet isn't recommended now, for obvious reasons (including that it's a bit too slow for testing).

#### Use of wallets

** Wallet type** - please stick with native segwit (`native=true` in config *before* you generate), but you can also choose p2sh-p2wpkh, it should work. No other script type (including p2pkh) will work here. We don't want mixed script type SNICKER coinjoins.

**Persistence** - this is very important and not at all obvious! But, on regtest by default (and I think testnet? check), we use hex seeds instead of wallet files and `VolatileStorage` (wallet storage in memory; wiped on shutdown). This is fine and convenient for many tests, but will not work for a key part of SNICKER - imported keys.
The upshot - **make sure you actually generate wallet files for all wallets you're going to test SNICKER with**, otherwise you will not even see the created coins on the receiver side.
Additionally, when you view the wallet with wallet-tool, you need to use `--recoversync`, as the default fast sync won't see imported keys.

#### A possible test workflow

Generate a minimum of two joinmarket wallets with `python wallet-tool.py generate`, as noted above, native (or at least, both the same type).

Fund them both. They won't need more than one funding utxo to start with.

Start the test server. Navigate to `scripts/snicker` and run `python snicker-server.py` - no arguments should be needed, and this will generate an onion running serving on port 80; the onion hostname is displayed:

```
(jmvenv) waxwing@here~/testjminstall/joinmarket-clientserver/scripts/snicker$ python snicker-server.py 
User data location: 
Attempting to start onion service on port: 80 ...
Your hidden service is available: 
xpkqk2cy2h2ay5iecwcod5ka36nxj2tsiyczk2w5c6o7h5g57w3xg4id.onion
```

This is ephemeral, obviously we intend these servers to be long-running later. For now, add that onion **including an http prefix** here:

```

[SNICKER]
enabled = true
servers= http://xpkqk2cy2h2ay5iecwcod5ka36nxj2tsiyczk2w5c6o7h5g57w3xg4id.onion,
```
... to a `joinmarket.cfg` that you add inside `scripts/snicker`, by copying it from `scripts/` or wherever you keep your testing `joinmarket.cfg` file. (This manual annoyance is part of testing, it won't be needed in mainnet usage of course)

`servers=` there is a comma separated list, and for now (until bugfixed) you need to include `http://`.

You're now ready to do the two steps: (a) create a proposal and upload it, (b) download proposals and complete coinjoins. It could be different people doing (a) and (b) of course but here we're assuming one tester doing everything (see two wallets above).

##### Creating one or more proposals

First you need a candidate. Scanning the blockchain or other data to find candidate transactions is functionality that is not (yet?) included in this Joinmarket code), but for testing we can create something ourselves.
Assuming (wallet1.jmdat : **proposer wallet**, wallet2.jmdat: **receiver wallet**):
Create a transaction in wallet2.jmdat, e.g.:

```
python sendpayment.py --datadir=. -N0 -m0 wallet2.jmdat 0.26 bcrt1qwxcf47avvgzxyu39cy8n4r22qaynvn7mc359ap
```

The console output will include e.g. : 
```
2020-12-16 11:13:01,708 [INFO]  {
    "hex": "0200000000010138e8a90b3df7740b9d5f5ae9af2cf6769f314d290b2e12bf25bfa4aae2c0cbe20000000000feffffff0280ba8c010000000016001471b09afbac6204627225c10f3a8d4a0749364fdb6d7c36220000000016001447ae59f32c504cbb56e18b77f7842fb58b55025b02473044022075354351ad4c619ba662f9abd25e8ee434f8381795001606a29fa959d36aeb7f022018f8bf1ec0407dad586baeb7e4d977aaacbd8fb15579293e6d739ad69ac3c6cf012103f8e827464fb83209c194376c53ae8f4e7ab5f1baf0948705fec6dd421f2b65c37a020000",
    "inputs": [
        .................
```

Copy that fully signed transaction hex (after broadcasting the transaction, of course).

In the outputs section of the above transaction (as shown in the console), check the output index of the output you want to do the SNICKER with.
Then, using first wallet `wallet1.jmdat` you can run the `create-proposals.py` script from `scripts/snicker`:

```
python create-snicker-proposal.py --datadir=. wallet1.jmdat -m0 "0200000000010138e8a90b3df7740b9d5f5ae9af2cf6769f314d290b2e12bf25bfa4aae2c0cbe20000000000feffffff0280ba8c010000000016001471b09afbac6204627225c10f3a8d4a0749364fdb6d7c36220000000016001447ae59f32c504cbb56e18b77f7842fb58b55025b02473044022075354351ad4c619ba662f9abd25e8ee434f8381795001606a29fa959d36aeb7f022018f8bf1ec0407dad586baeb7e4d977aaacbd8fb15579293e6d739ad69ac3c6cf012103f8e827464fb83209c194376c53ae8f4e7ab5f1baf0948705fec6dd421f2b65c37a020000" 0 0 100
```

Here, the last three arguments are (input index), (output index) and (sats to pay to the receiver). The former can be zero always if the initial transaction is *not* a coinjoin (indeed, in our case, there was only 1 input, so it was easy), the second is the output index that you recorded above (it's the index of the output that we are asking the receiver to spend), and the last you can choose whatever you like, including negative integers.

*Current bug* : when you run the above, assuming it connects the server OK, you will see:

```
Response from server: http://xpkqk2cy2h2ay5iecwcod5ka36nxj2tsiyczk2w5c6o7h5g57w3xg4id.onion was: proposals-accepted
```
... but it will hang and not quit. Just Ctrl-C to quit until that bug is fixed (the "proposals-accepted" at least tells you that the proposal was recorded).

##### Receiving the created proposals.

The last phase is pretty simple, if it works, just run the receiver script (from `scripts/snicker`) as follows:

```
python receive-snicker.py --datadir=. wallet2.jmdat
User data location: .
2020-12-16 11:43:03,779 [DEBUG]  rpc: getblockchaininfo []
2020-12-16 11:43:03,781 [DEBUG]  rpc: getnewaddress []
Enter passphrase to decrypt wallet: 
2020-12-16 11:43:07,501 [DEBUG]  rpc: listaddressgroupings []
2020-12-16 11:43:07,562 [DEBUG]  Fast sync in progress. Got this many used addresses: 3
2020-12-16 11:43:08,075 [DEBUG]  rpc: listunspent [0]
2020-12-16 11:43:08,216 [DEBUG]  bitcoind sync_unspent took 0.14214825630187988sec
2020-12-16 11:43:08,280 [WARNING]  Cannot listen on port 27183, trying next port
2020-12-16 11:43:08,281 [WARNING]  Cannot listen on port 27184, trying next port
2020-12-16 11:43:08,281 [WARNING]  Cannot listen on port 27185, trying next port
2020-12-16 11:43:08,281 [INFO]  Listening on port 27186
2020-12-16 11:43:08,282 [INFO]  (SNICKER) Listening on port 26186
2020-12-16 11:43:08,282 [INFO]  Starting transaction monitor in walletservice
2020-12-16 11:43:08,339 [INFO]  Starting SNICKER polling loop
2020-12-16 11:43:22,676 [DEBUG]  rpc: sendrawtransaction ['020000000001028ffa6a6f0184ed8123993273ecbb4af82d1b1c0963c815fec4e92525eaba56b30000000000ffffffffa5015509e0e241ef25ee7ccc1936295c908e572cb222105e16c197d66f0599640000000000ffffffff03e4ba8c0100000000160014190ec76b7843f47bc367b65119b98c32074536255dfd5e0a00000000160014d38fa4a6ac8db7495e5e2b5d219dccd412dd9baee4ba8c01000000001600147b4676f859b993257bc8d5880650fcab470db8a1024830450221008480d553177a020f58ca0e45b9e20aa027305a279a3de1014f55ff22909b89b1022054e848285ee60c169b5de19bb4d3637b606ff14bc4cca4506ad05a42fff6af400121029a82a00f05d023f188dfd1db82ef8ec136b0500bbd33bb1f65930c5b74e3199802463043021f01d3f4567c32fc0c5c0cd33db233a3c74100a36940d743b72042b55e60b89d022073ab203ad0fee389f2a2c9e62197244cea95b07ae78a5516ca9f866a8e348d2c01210245d8623c4b06505dffd21bdd314a84b73afe2b9d49a93fe89397b48a85b718bd00000000']
2020-12-16 11:43:22,678 [INFO]  Successfully broadcast SNICKER coinjoin: 33ec857df09030140391529295412434cced8191626024f937426b7859a21947
2020-12-16 11:43:23,359 [INFO]  Removed utxos=
b356baea2525e9c4fe15c863091c1b2df84abbec7332992381ed84016f6afa8f:0 - path: m/84'/1'/4'/0/0, address: bcrt1qwxcf47avvgzxyu39cy8n4r22qaynvn7mc359ap, value: 26000000
2020-12-16 11:43:23,360 [INFO]  Added utxos=
33ec857df09030140391529295412434cced8191626024f937426b7859a21947:0 - path: imported/1/0, address: bcrt1qry8vw6mcg068hsm8keg3nwvvxgr52d3923gg45, value: 26000100
```

Obviously this is the ideal case: if no errors occur. If invalid proposals, or proposals on coins that no longer exist because you already spent them, are encountered, logging messages are displayed to that effect.
(This data will all be added to a SNICKER log file shortly, but that doesn't exist yet.)

### What kind of testing is useful?

Pretty much anything at this early stage. As well as testing, if others can help build out infrastructure for scanning blocks for candidates, especially *SNICKER* candidates (see the draft BIP mentioned at the start for the transaction format), and for making a more useful-in-the-real-world server script which does simple things like managing its database size and preventing crude DOS, that would be helpful.

##### Appendix: Example output of SNICKER

This is what is produced by `print(jmbitcoin.human_readable_transaction(jmbitcoin.CTransaction.deserialize(jmbase.hextobin('020000000001028ffa6a6f0184ed8123993273ecbb4af82d1b1c0963c815fec4e92525eaba56b30000000000ffffffffa5015509e0e241ef25ee7ccc1936295c908e572cb222105e16c197d66f0599640000000000ffffffff03e4ba8c0100000000160014190ec76b7843f47bc367b65119b98c32074536255dfd5e0a00000000160014d38fa4a6ac8db7495e5e2b5d219dccd412dd9baee4ba8c01000000001600147b4676f859b993257bc8d5880650fcab470db8a1024830450221008480d553177a020f58ca0e45b9e20aa027305a279a3de1014f55ff22909b89b1022054e848285ee60c169b5de19bb4d3637b606ff14bc4cca4506ad05a42fff6af400121029a82a00f05d023f188dfd1db82ef8ec136b0500bbd33bb1f65930c5b74e3199802463043021f01d3f4567c32fc0c5c0cd33db233a3c74100a36940d743b72042b55e60b89d022073ab203ad0fee389f2a2c9e62197244cea95b07ae78a5516ca9f866a8e348d2c01210245d8623c4b06505dffd21bdd314a84b73afe2b9d49a93fe89397b48a85b718bd00000000'))))`:

```
{
    "hex": "02000000000102578770b2732aed421ffe62d54fd695cf281ca336e4f686d2adbb2e8c3bedb2570000000000ffffffff4719a259786b4237f92460629181edcc3424419592529103143090f07d85ec330100000000ffffffff0324fd9b0100000000160014d38fa4a6ac8db7495e5e2b5d219dccd412dd9bae24fd9b0100000000160014564aead56de8f4d445fc5b74a61793b5c8a819667af6c208000000001600146ec55c2e1d1a7a868b5ec91822bf40bba842bac502473044022078f8106a5645cc4afeef36d4addec391a5b058cc51053b42c89fcedf92f4db1002200cdf1b66a922863fba8dc1b1b1a0dce043d952fa14dcbe86c427fda25e930a53012102f1f750bfb73dbe4c7faec2c9c301ad0e02176cd47bcc909ff0a117e95b2aad7b02483045022100b9a6c2295a1b0f7605381d416f6ed8da763bd7c20f2402dd36b62dd9dd07375002207d40eaff4fc6ee219a7498abfab6bdc54b7ce006ac4b978b64bff960fbf5f31e012103c2a7d6e44acdbd503c578ec7d1741a44864780be0186e555e853eee86e06f11f00000000",
    "inputs": [
        {
            "outpoint": "57b2ed3b8c2ebbadd286f6e436a31c28cf95d64fd562fe1f42ed2a73b2708757:0",
            "scriptSig": "",
            "nSequence": 4294967295,
            "witness": "02473044022078f8106a5645cc4afeef36d4addec391a5b058cc51053b42c89fcedf92f4db1002200cdf1b66a922863fba8dc1b1b1a0dce043d952fa14dcbe86c427fda25e930a53012102f1f750bfb73dbe4c7faec2c9c301ad0e02176cd47bcc909ff0a117e95b2aad7b"
            },
        {
            "outpoint": "33ec857df09030140391529295412434cced8191626024f937426b7859a21947:1",
            "scriptSig": "",
            "nSequence": 4294967295,
            "witness": "02483045022100b9a6c2295a1b0f7605381d416f6ed8da763bd7c20f2402dd36b62dd9dd07375002207d40eaff4fc6ee219a7498abfab6bdc54b7ce006ac4b978b64bff960fbf5f31e012103c2a7d6e44acdbd503c578ec7d1741a44864780be0186e555e853eee86e06f11f"
        }
        ],
    "outputs": [
        {
            "value_sats": 27000100,
            "scriptPubKey": "0014d38fa4a6ac8db7495e5e2b5d219dccd412dd9bae",
            "address": "bc1q6w86ff4v3km5jhj79dwjr8wv6sfdmxaw2dytjc"
            },
        {
            "value_sats": 27000100,
            "scriptPubKey": "0014564aead56de8f4d445fc5b74a61793b5c8a81966",
            "address": "bc1q2e9w44tdar6dg30utd62v9unkhy2sxtxtqrthh"
            },
        {
            "value_sats": 146994810,
            "scriptPubKey": "00146ec55c2e1d1a7a868b5ec91822bf40bba842bac5",
            "address": "bc1qdmz4ctsarfagdz67eyvz906qhw5y9wk9dqpuea"
        }
        ],
    "txid": "ca606efc5ba8f6669ba15e9262e5d38e745345ea96106d5a919688d1ff0da0cc",
    "nLockTime": 0,
    "nVersion": 2
}
```

