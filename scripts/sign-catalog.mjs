import { createHash, createPrivateKey, sign } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import process from 'node:process'

const [catalogPath = 'catalog.json', signaturePath = 'catalog.sig.json'] = process.argv.slice(2)
const catalogBytes = await readFile(catalogPath)
const catalog = JSON.parse(catalogBytes.toString('utf8'))
validateCatalog(catalog)

const signingKeys = [
  readSigningKey('PLUGIN_CATALOG_SIGNING_KEY_ID', 'PLUGIN_CATALOG_SIGNING_KEY_PEM', true),
  readSigningKey('PLUGIN_CATALOG_SECONDARY_KEY_ID', 'PLUGIN_CATALOG_SECONDARY_KEY_PEM', false),
].filter(Boolean)

const signatures = signingKeys.map(({ id, key }) => ({
  key_id: id,
  signature: toPaddedBase64URL(sign(null, catalogBytes, key)),
}))
const envelope = {
  signature_version: 1,
  algorithm: 'ed25519',
  catalog_sha256: createHash('sha256').update(catalogBytes).digest('hex'),
  key_id: signatures[0].key_id,
  signatures,
}
await writeFile(signaturePath, `${JSON.stringify(envelope, null, 2)}\n`, 'utf8')

function readSigningKey(idName, keyName, required) {
  const id = String(process.env[idName] ?? '').trim()
  const pem = String(process.env[keyName] ?? '').replaceAll('\\n', '\n').trim()
  if (!id && !pem && !required) return null
  if (!/^[a-z0-9][a-z0-9._-]{0,63}$/.test(id) || !pem) {
    throw new Error(`${idName} and ${keyName} must be configured together`)
  }
  const key = createPrivateKey(pem)
  if (key.asymmetricKeyType !== 'ed25519') {
    throw new Error(`${keyName} must contain an Ed25519 private key`)
  }
  return { id, key }
}

function validateCatalog(catalog) {
  if (catalog?.catalog_version !== '1' || !Array.isArray(catalog.entries)) {
    throw new Error('catalog.json must satisfy catalog version 1')
  }
  const pluginIDs = new Set()
  for (const entry of catalog.entries) {
    if (!/^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$/.test(entry?.id ?? '') || pluginIDs.has(entry.id)) {
      throw new Error(`invalid or duplicate plugin id: ${entry?.id ?? ''}`)
    }
    pluginIDs.add(entry.id)
    if (!String(entry.repository_url ?? '').startsWith('https://') || !Array.isArray(entry.releases)) {
      throw new Error(`plugin ${entry.id} has invalid repository or releases metadata`)
    }
    const versions = new Set()
    for (const release of entry.releases) {
      if (versions.has(release.version)) throw new Error(`plugin ${entry.id} has duplicate release ${release.version}`)
      versions.add(release.version)
      const platforms = new Set()
      for (const asset of release.assets ?? []) {
        if (platforms.has(asset.platform) || !String(asset.url ?? '').startsWith('https://')) {
          throw new Error(`plugin ${entry.id} release ${release.version} has invalid assets`)
        }
        platforms.add(asset.platform)
      }
    }
  }
}

function toPaddedBase64URL(value) {
  return value.toString('base64').replaceAll('+', '-').replaceAll('/', '_')
}

