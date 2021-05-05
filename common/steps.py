import logging
import os
import json

import dataset


class SetupDatabase(object):
    def run(self, context):
        home_dir = os.getenv("HOME")
        args = context["args"]
        coin = args.coin
        stable_currency = args.stable_coin
        table_name = "{}_{}_trades".format(coin.lower(), stable_currency.lower())
        db_file = context["args"].db_file
        db_connection_string = f"sqlite:///{home_dir}/{db_file}"
        db = dataset.connect(db_connection_string)
        context["db_table"] = db.create_table(table_name)
        logging.info(
            f"Connecting to database {db_connection_string} and table {table_name}"
        )


class PrintContext(object):
    def run(self, context):
        data = {}
        if "data" in context:
            data = context.get("data", {})
            del context["data"]
        logging.info(context)
        logging.info(json.dumps(data, indent=4))
