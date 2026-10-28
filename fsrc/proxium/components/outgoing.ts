import type { RaRecord } from 'react-admin'

// How the proxy picks the IP it connects to targets from, as the API names the modes.
export const OUTGOING_MODES = [
  { id: 'system', name: 'System' },
  { id: 'listener', name: 'Listener' },
  { id: 'pool', name: 'Pool' },
]

// What to do about an IP some proxy doesn't have, e.g. in a tooltip.
export const MISSING_IP_HELP =
  'Connections from this IP fail on proxies without it. Add it to their servers, ' +
  'in Docker run them with --network host. Proxy instances list the IPs each one has.'

export type IPAvailability = 'everywhere' | 'somewhere' | 'nowhere'

/**
 * Whether the pending and running proxies have the outgoing IP, from `liveInstances` and
 * `instancesWithoutIp`. Undefined with no proxy running: nothing to check against.
 */
export const ipAvailability = (record: RaRecord): IPAvailability | undefined => {
  if (record.liveInstances === 0) {
    return undefined
  }
  if (record.instancesWithoutIp === 0) {
    return 'everywhere'
  }
  return record.instancesWithoutIp === record.liveInstances ? 'nowhere' : 'somewhere'
}

/** What's wrong with the outgoing IP, undefined if nothing is. */
export const missingIpText = (record: RaRecord): string | undefined => {
  switch (ipAvailability(record)) {
    case 'nowhere':
      return record.liveInstances === 1 ? 'Not on the proxy' : 'Not on any proxy'
    case 'somewhere':
      return `Not on ${record.instancesWithoutIp} of ${record.liveInstances} proxies`
    default:
      return undefined
  }
}

/** An outgoing IP in a picker, with what's wrong with it. */
export const outgoingIpText = (record: RaRecord) =>
  [record.ip, record.name, missingIpText(record)].filter(Boolean).join(' · ')
