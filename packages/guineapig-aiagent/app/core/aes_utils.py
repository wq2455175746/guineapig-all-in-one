import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


def decrypt(data, aes_key_base64):
    if data is None:
        return data
    # 解码Base64格式的密钥
    aes_key = base64.b64decode(aes_key_base64)
    # 解码Base64格式的数据
    encrypted_data = base64.b64decode(data)
    cipher = AES.new(aes_key, 1)
    # 解密数据并去除填充
    decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)
    # 将解密后的字节数据转换为字符串
    return decrypted_data.decode("utf-8")
