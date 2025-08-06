import base64, os
from lib.authenticatedencryption import AuthenticatedEncryption
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

def encrypt_with_public_key(public_key: dict, data: str) -> str:
    modulus_bytes = base64.b64decode(public_key['modulus'])
    exponent_bytes = base64.b64decode(public_key['exponent'])
    public_key = rsa.RSAPublicNumbers(
        int.from_bytes(exponent_bytes, 'big'),
        int.from_bytes(modulus_bytes, 'big')
    ).public_key(default_backend())

    key_enc = os.urandom(32)
    key_mac = os.urandom(64)
    
    cipher_text = AuthenticatedEncryption().encrypt(key_enc, key_mac, data.encode('utf-8'))

    keys = bytearray([0] * (len(key_enc) + len(key_mac) + 2))

    keys[0] = 0
    keys[1] = 1

    keys[2: len(key_enc) + 2] = key_enc[0: len(key_enc)]
    keys[len(key_enc) + 2: len(key_enc) + len(key_mac) + 2] = key_mac[0: len(key_mac)]

    encrypted_bytes = public_key.encrypt(bytes(keys),
                                             padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                                                          algorithm=hashes.SHA256(),
                                                          label=None))

    return base64.b64encode(encrypted_bytes).decode() + base64.b64encode(cipher_text).decode()