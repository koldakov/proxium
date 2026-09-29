import { useEffect, useState } from 'react'

import { ipNetwork } from '../../components/validators'

const validateNetwork = ipNetwork()

/** `value` once it stops changing for `delay` ms, e.g. a network being typed. */
export const useDebounced = <T>(value: T, delay = 300) => {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timeout)
  }, [value, delay])
  return debounced
}

/** A valid network, worth asking the API about. */
export const isComplete = (network: string) =>
  network !== '' && validateNetwork(network) === undefined

/** `3 active networks`. */
export const countNetworks = (count: number, adjective = '') =>
  `${count} ${adjective}${adjective && ' '}network${count === 1 ? '' : 's'}`
