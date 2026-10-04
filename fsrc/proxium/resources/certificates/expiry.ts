import type { RaRecord } from 'react-admin'

// Time to get and activate a new certificate before clients start refusing the old one.
const EXPIRING_SOON_DAYS = 14

const DAY_MS = 24 * 60 * 60 * 1000

export const isExpired = (record: RaRecord): boolean => new Date(record.notValidAfter) <= new Date()

export const isExpiringSoon = (record: RaRecord): boolean =>
  !isExpired(record) &&
  new Date(record.notValidAfter).getTime() - Date.now() < EXPIRING_SOON_DAYS * DAY_MS

// E.g. "proxy.example.com, 203.0.113.10". A certificate without names is still told apart by its fingerprint.
export const describeCertificate = (record: RaRecord): string =>
  record.names.length > 0
    ? record.names.join(', ')
    : `No names, ${record.fingerprint.slice(0, 16)}…`
