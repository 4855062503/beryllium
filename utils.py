import re
import io
import decimal
import base64
import secrets
import string

import qrcode
import qrcode.image.svg
import qrcode.image.pil

def generate_key(chars: int = 10, upper: bool = True) -> str:
    alphabet = string.ascii_letters + string.digits
    if upper:
        alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(chars))

def is_email(val: str):
    return re.match("[^@]+@[^@]+\.[^@]+", val) # pylint: disable=anomalous-backslash-in-string

def is_mobile(val: str):
    return val.isnumeric()

def qrcode_create(factory, data: str, box_size: int) -> io.BytesIO:
    img = qrcode.make(data, image_factory=factory, box_size=box_size)
    output = io.BytesIO()
    img.save(output)
    return output

def qrcode_svg_create(data: str, box_size: int = 10) -> str:
    factory = qrcode.image.svg.SvgPathImage
    output = qrcode_create(factory, data, box_size)
    svg = output.getvalue().decode('utf-8')
    return svg

def qrcode_pngb64_create(data: str, box_size: int = 10) -> str:
    factory = qrcode.image.pil.PilImage
    output = qrcode_create(factory, data, box_size)
    b64 = base64.b64encode(output.getvalue()).decode('utf-8')
    return b64

def round_dec(value: decimal.Decimal, places: int) -> decimal.Decimal:
    fmt = '.' + (places - 1) * '0' + '1'
    return value.quantize(decimal.Decimal(fmt), rounding=decimal.ROUND_DOWN)
