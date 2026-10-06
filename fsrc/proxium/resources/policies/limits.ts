import type { RaRecord } from 'react-admin'

// What a limit is counted over, as the API names it: connections with the same value share it.
export const LIMIT_SCOPES = [
  { id: 'identity', name: 'Per account or network' },
  { id: 'client_ip', name: 'Per client IP' },
  { id: 'target_host', name: 'Per target host' },
  { id: 'connection', name: 'Per connection' },
  { id: 'global', name: 'Whole proxy' },
]

export const DIRECTIONS = [
  { id: 'both', name: 'Each way' },
  { id: 'received', name: 'Download' },
  { id: 'sent', name: 'Upload' },
]

// The API counts bytes per second, people think in Mbit/s.
const BYTES_PER_MBIT = 1_000_000 / 8

export const formatMbits = (bytes: number | null | undefined) =>
  bytes == null ? '' : bytes / BYTES_PER_MBIT

export const parseMbits = (value: string) =>
  value === '' ? null : Math.round(parseFloat(value) * BYTES_PER_MBIT)

export const formatMegabytes = (bytes: number | null | undefined) =>
  bytes == null ? '' : bytes / 1_000_000

export const parseMegabytes = (value: string) =>
  value === '' ? null : Math.round(parseFloat(value) * 1_000_000)

/**
 * The form edits one rule that always applies: conditions aren't there yet, so a second rule would never match.
 * Fills what the form leaves out: the rule's name and a burst of one second of the rate.
 */
export const toPolicyData = (data: Partial<RaRecord>) => {
  const [first = {}, ...rest] = data.rules ?? []
  const rule = {
    ...first,
    name: first.name ?? 'Always',
    connectionLimits: first.connectionLimits ?? [],
    speedLimits: (first.speedLimits ?? []).map((limit: RaRecord) => ({
      ...limit,
      burst: limit.burst ?? limit.rate,
    })),
  }
  return { ...data, rules: [rule, ...rest] }
}
