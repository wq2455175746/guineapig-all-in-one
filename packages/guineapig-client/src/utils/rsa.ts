import JSEncrypt from 'jsencrypt'

let publicKey: string | null = null

async function loadPublicKey(): Promise<string> {
  if (publicKey) return publicKey

  const res = await fetch('/public.key')
  if (!res.ok) {
    throw new Error('无法加载公钥文件 public.key')
  }
  publicKey = await res.text()
  return publicKey
}

let encryptInstance: JSEncrypt | null = null

async function getEncryptor(): Promise<JSEncrypt> {
  if (encryptInstance) return encryptInstance

  const key = await loadPublicKey()
  const jsEncrypt = new JSEncrypt({})
  jsEncrypt.setPublicKey(key)
  encryptInstance = jsEncrypt
  return encryptInstance
}

/**
 * 使用 RSA 公钥加密明文 (PKCS#1 v1.5)
 * 返回 Base64 编码的密文
 */
export async function encryptApiKey(plaintext: string): Promise<string> {
  const encryptor = await getEncryptor()
  const encrypted = encryptor.encrypt(plaintext)
  if (!encrypted) {
    throw new Error('RSA 加密失败')
  }
  return encrypted
}
