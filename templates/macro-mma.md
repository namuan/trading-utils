## {{ now().strftime('%B %Y') }} Sectors Multiple Moving Averages

### Sectors

{% for stock in stocks["sector_stocks"] %}
![]({{ stock }}-mma.png)
{% endfor %}

> Risk Warning: We do not guarantee accuracy and will not accept liability for any loss or damage which arise directly or indirectly from use of or reliance on information contained within these reports. We may provide general commentary which is not intended as investment advice and must not be construed as such. Trading/Investments carries a risk of losses in excess of your deposited funds and may not be suitable for all investors. Please ensure that you fully understand the risks involved.
