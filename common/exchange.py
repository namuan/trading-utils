import ccxt

from common.environment import EXCHANGE_API_KEY, EXCHANGE_API_SECRET


def exchange_factory(exchange_id):
    exchange_clazz = getattr(ccxt, exchange_id)
    return exchange_clazz({"apiKey": EXCHANGE_API_KEY, "secret": EXCHANGE_API_SECRET})
