def __init__(self, options_data, spot_price):
    """
    Initialize the OptionPlot object.

    :param options_data: A list of option contracts.
    :type options_data: list[OptionContract]
    :param spot_price: The current spot price.
    :type spot_price: float
    """
    self.options_data = options_data
    self.spot_price = spot_price
    # Assuming strike_range is a list of strike prices
    self.strike_range = [option.strike_price for option in options_data]
