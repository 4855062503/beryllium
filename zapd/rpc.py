#!/usr/bin/python3

import sys
import logging
import json
import struct

import gevent
from gevent.pywsgi import WSGIServer
from flask import Flask
from flask_jsonrpc import JSONRPC
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import base58
import pywaves
import pyblake2

import config
from database import db_session, init_db
import db_settings
from models import Transaction, CreatedTransaction
import utils

cfg = config.read_cfg()
init_db()
app = Flask(__name__)
jsonrpc = JSONRPC(app, "/api")
logger = logging.getLogger(__name__)

# our address object
pw_address = None

@jsonrpc.method("balance")
def balance():
    path = f"assets/balance/{cfg.address}/{cfg.asset_id}"
    response = requests.get(cfg.node_http_base_url + path)
    return response.json()

@jsonrpc.method("listtransactions")
def listtransactions(invoice_id):
    txs = Transaction.from_invoice_id(db_session, invoice_id)
    txs_json = []
    for tx in txs:
        txs_json.append(tx.to_json())
    return txs_json

def transfer_asset_txid(tx):
    serialized_data = b'\4' + \
        base58.b58decode(tx["senderPublicKey"]) + \
        (b'\1' + base58.b58decode(tx["assetId"]) if tx["assetId"] else b'\0') + \
        (b'\1' + base58.b58decode(tx["feeAssetId"]) if tx["feeAssetId"] else b'\0') + \
        struct.pack(">Q", tx["timestamp"]) + \
        struct.pack(">Q", tx["amount"]) + \
        struct.pack(">Q", tx["fee"]) + \
        base58.b58decode(tx["recipient"]) + \
        struct.pack(">H", len(tx["attachment"])) + \
        pywaves.crypto.str2bytes(tx["attachment"])
    return utils.txid_from_txdata(serialized_data)

@jsonrpc.method("createtransaction")
def createtransaction(recipient, amount, attachment):
    recipient = pywaves.Address(recipient)
    address_data = pw_address.sendAsset(recipient, pywaves.Asset(cfg.asset_id), amount, attachment)
    signed_tx = json.loads(address_data["api-data"])
    # calc txid properly
    txid = transfer_asset_txid(signed_tx)
    # store tx in db
    dbtx = CreatedTransaction(txid, "created", signed_tx["amount"], address_data["api-data"])
    db_session.add(dbtx)
    db_session.commit()
    # return txid/state to caller
    return {"txid": txid, "state": dbtx.state}

@jsonrpc.method("broadcasttransaction")
def broadcasttransaction(txid):
    dbtx = CreatedTransaction.from_txid(db_session, txid)
    signed_tx = dbtx.json_data
    # broadcast
    logger.debug(f"requesting broadcast of tx:\n\t{signed_tx}")
    path = f"assets/broadcast/transfer"
    headers = {"Content-Type": "application/json"}
    response = requests.post(cfg.node_http_base_url + path, headers=headers, data=signed_tx)
    if response.ok:
        # update tx in db
        dbtx.state = "broadcast"
    else:
        logger.error(f"broadcast tx ({response.status_code}, {response.request.method} {response.url}):\n\t{response.text}")
    db_session.add(dbtx)
    db_session.commit()
    # return txid/state to caller
    return {"txid": txid, "state": dbtx.state}

def get(url):
    with requests.Session() as s:
        retries = Retry(
            total=10,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504])
        s.mount('http://', HTTPAdapter(max_retries=retries))
        s.mount('https://', HTTPAdapter(max_retries=retries))
        response = s.get(url)
        return response

def block_height():
    response = get(cfg.node_http_base_url + "blocks/height")
    return response.json()["height"]

def block_at(num):
    response = get(cfg.node_http_base_url + f"blocks/at/{num}")
    return response.json()

class ZapRPC():

    def __init__(self, addr="127.0.0.1", port=5000):
        self.addr = addr
        self.port = port

    def start(self, group=None):
        # get node addresses
        response = requests.get(cfg.node_http_base_url + "addresses")
        node_addresses = response.json()
        # check cfg.address is one of the nodes addresses
        if not cfg.address in node_addresses:
            logger.error(f"node wallet does not control {cfg.address}")
            sys.exit(1)
        # get private key from our node
        headers = {"X-Api-Key": cfg.node_api_key}
        response = requests.get(cfg.node_http_base_url + "wallet/seed", headers=headers)
        if not response.ok:
            logger.error(f"Wallet seed request: {response.text}")
            sys.exit(1)
        else:
            # create our address object for creating transactions
            wallet_seed = response.json()["seed"]
            global pw_address
            pw_address = pywaves.Address(seed=wallet_seed)
            # check address object matches our configured address
            if not pw_address.address != cfg.address:
                logger.error(f"pw_address does not match {cfg.address}")
                sys.exit(1)

        def runloop():
            logger.info("ZapRPC runloop started")

            http_server = WSGIServer((self.addr, self.port), app)
            http_server.serve_forever()

        def blockloop():
            logger.info("ZapRPC blockloop started")

            scanned_block_num = db_settings.get_scanned_block_num(cfg.start_block)
            while 1:
                gevent.sleep(5)
                # use "block_height() - 1" because with the WavesNG protocol the block can have new transactions
                # added until the next block is found
                while block_height() - 1 > scanned_block_num:
                    block = block_at(scanned_block_num + 1)
                    for tx in block["transactions"]:
                        if tx["type"] == 4:
                            recipient = tx["recipient"]
                            if recipient == cfg.address:
                                txid = tx["id"]
                                logger.info(f"new tx {txid}")
                                attachment = tx["attachment"]
                                if attachment:
                                    attachment = base58.b58decode(attachment)
                                    logger.info(f"    {attachment}")
                                invoice_id = utils.extract_invoice_id(logger, attachment)
                                if invoice_id:
                                    logger.info(f"    {invoice_id}")
                                dbtx = Transaction(txid, tx["sender"], recipient, tx["amount"], attachment, invoice_id, block["height"])
                                db_session.add(dbtx)
                    scanned_block_num = block["height"]
                    logger.debug(f"scanned block {scanned_block_num}")
                    if scanned_block_num % 100 == 0:
                        db_settings.set_scanned_block_num(db_session, scanned_block_num)
                        db_session.commit()
                    gevent.sleep(0)
                db_settings.set_scanned_block_num(db_session, scanned_block_num)
                db_session.commit()

        logger.info("spawning ZapRPC runloop...")
        self.runloop_greenlet = gevent.spawn(runloop)
        logger.info("spawning ZapRPC blockloop...")
        self.blockloop_greenlet = gevent.spawn(blockloop)
        if group != None:
            group.add(self.runloop_greenlet)
            group.add(self.blockloop_greenlet)
        gevent.sleep(0)

    def stop(self):
        self.runloop_greenlet.kill()
        self.blockloop_greenlet.kill()

if __name__ == "__main__":
    # setup logging
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(logging.Formatter('[%(name)s %(levelname)s] %(message)s'))
    logger.addHandler(ch)
    # clear loggers set by any imported modules
    logging.getLogger().handlers.clear()

    zaprpc = ZapRPC()
    zaprpc.start()

    while 1:
        gevent.sleep(1)

    zaprpc.stop()
