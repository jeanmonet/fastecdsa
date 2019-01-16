from binascii import a2b_base64, b2a_base64, hexlify
from textwrap import wrap

from . import KeyEncoder
from .asn1 import (
    BIT_STRING, OBJECT_IDENTIFIER, OCTET_STRING, PARAMETERS, PUBLIC_KEY, SEQUENCE,
    asn1_ecversion, asn1_oid, asn1_private_key, asn1_public_key, asn1_structure, parse_asn1_length
)
from .rfc5480 import EC_PUBLIC_FOOTER
from ..curve import Curve
from ..point import Point

EC_PRIVATE_HEADER = '-----BEGIN EC PRIVATE KEY-----'
EC_PRIVATE_FOOTER = '-----END EC PRIVATE KEY-----'


class RFC5915(KeyEncoder):
    def __init__(self):
        self.asn1_parsed_data = []

    def _parse_ascii_armored_base64(self, data):
        """Convert an ASCII armored key to raw binary data"""
        lines = (line for line in data.split('\n'))
        header = next(lines).rstrip()

        base64_data = ''
        line = next(lines).rstrip()

        while line and (line != EC_PRIVATE_FOOTER) and (line != EC_PUBLIC_FOOTER):
            base64_data += line
            line = next(lines).rstrip()

        return a2b_base64(base64_data)

    def _parse_asn1_structure(self, data):
        """Recursively parse ASN.1 data"""
        data_type = data[:1]
        length, data, remaining = parse_asn1_length(data[1:])

        if data_type in [OCTET_STRING, BIT_STRING, OBJECT_IDENTIFIER]:
            self.asn1_parsed_data.append((data_type, data))
        elif data_type in [SEQUENCE, PUBLIC_KEY, PARAMETERS]:
            self._parse_asn1_structure(data)

        if remaining:
            self._parse_asn1_structure(remaining)

    def encode_private_key(self, d, Q=None, curve=None):
        """Encode an EC keypair as described in `RFC 5915 <https://tools.ietf.org/html/rfc5915.html>`_.

        Args:
            | d (long): An ECDSA private key.
            | Q (fastecdsa.point.Point): The ECDSA public key.
            | curve (fastecdsa.curve.Curve): The curve that the private key is for.

        Returns:
            str: The ASCII armored encoded EC keypair.
        """
        if Q is None and curve is None:
            raise ValueError('Ambiguous encoding, public key or curve must passed as an argument')
        elif Q is None:
            Q = d * curve.G

        version = asn1_ecversion()
        private_key = asn1_private_key(d, Q.curve)
        oid = asn1_oid(Q.curve)
        parameters = asn1_structure(PARAMETERS, oid)
        public_key_bitstring = asn1_public_key(Q)
        public_key = asn1_structure(PUBLIC_KEY, public_key_bitstring)

        sequence = version + private_key + parameters + public_key
        ec_private_key = asn1_structure(SEQUENCE, sequence)
        b64_data = '\n'.join(wrap(b2a_base64(ec_private_key).decode(), 64))

        return EC_PRIVATE_HEADER + '\n' + b64_data + '\n' + EC_PRIVATE_FOOTER

    def decode_private_key(self, pemdata):
        """Decode an EC key as described in `RFC 5915 <https://tools.ietf.org/html/rfc5915.html>`_ and
        `RFC 5480 <https://tools.ietf.org/html/rfc5480>`_.

        Args:
            pemdata (bytes): A sequence of bytes representing an encoded EC key.

        Returns:
            (long, fastecdsa.point.Point): A private key, public key tuple. If the encoded key was a
            public key the first entry in the tuple is None.
        """
        pemdata = self._parse_ascii_armored_base64(pemdata)
        self._parse_asn1_structure(pemdata)

        d, x, y, curve = None, None, None, None
        for (value_type, value) in self.asn1_parsed_data:
            if value_type == OCTET_STRING:
                d = int(hexlify(value), 16)
            elif value_type == OBJECT_IDENTIFIER and curve is None:
                curve = Curve.get_curve_by_oid(value)
            elif value_type == BIT_STRING:
                value = value.lstrip(b'\x00\x04')
                x = int(hexlify(value[:len(value) // 2]), 16)
                y = int(hexlify(value[len(value) // 2:]), 16)

        self.asn1_parsed_data = []
        Q = None if (x is None) or (y is None) else Point(x, y, curve)
        return d, Q

    def decode_public_key(self, pemdata):
        """Delegate to private key decoding but return only the public key"""
        _, Q = self.decode_private_key(pemdata)
        return Q

    def encode_public_key(self, Q):
        raise NotImplementedError(
            'RFC5915 does not define an encoding for public EC keys (try using RFC5480)')