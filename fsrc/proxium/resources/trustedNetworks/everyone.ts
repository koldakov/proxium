import ipaddr from 'ipaddr.js'
import type { RaRecord } from 'react-admin'

import { toCidr } from '../../components/validators'
import { isComplete } from './overlaps'

/** A valid /0 network: every address of its family. */
export const isEveryone = (network: string | undefined) => {
  const value = (network ?? '').trim()
  return isComplete(value) && ipaddr.parseCIDR(toCidr(value))[1] === 0
}

/** Active and /0: anyone on the internet gets in. */
export const isOpenToEveryone = (values: Partial<RaRecord> | undefined) =>
  values !== undefined && Boolean(values.isActive) && isEveryone(values.network)
