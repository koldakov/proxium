import ipaddr from 'ipaddr.js'

/** Rejects a date not in the future. Empty passes: pair with `required()` if needed. */
export const future = () => (value: string | null) =>
  value && new Date(value) <= new Date() ? 'Must be in the future' : undefined

const NETWORK_FORMAT = 'Must be a network like 10.0.0.0/8 or an address like 10.0.0.5'

/** CIDR notation, with a bare address taken as a single-address network, like the API does. */
export const toCidr = (value: string) =>
  value.includes('/') ? value : `${value}/${value.includes(':') ? 128 : 32}`

// Four-part decimal only: the API refuses shorthands like 10.1 or octal 010.0.0.1.
const isValidCidr = (cidr: string) =>
  cidr.includes(':') ? ipaddr.IPv6.isValidCIDR(cidr) : ipaddr.IPv4.isValidCIDRFourPartDecimal(cidr)

/** Checks an IPv4 or IPv6 network or address the way the API does, host bits included. Empty passes. */
export const ipNetwork = () => (value: string | null) => {
  if (!value) {
    return undefined
  }
  const cidr = toCidr(value)
  if (!isValidCidr(cidr)) {
    return NETWORK_FORMAT
  }

  // The API rejects an address inside the network, e.g. 10.0.0.1/8: suggest where the network starts.
  const [address, prefix] = ipaddr.parseCIDR(cidr)
  const start =
    address.kind() === 'ipv6'
      ? ipaddr.IPv6.networkAddressFromCIDR(cidr)
      : ipaddr.IPv4.networkAddressFromCIDR(cidr)
  if (start.toNormalizedString() !== address.toNormalizedString()) {
    return `The network starts at ${start.toString()}/${prefix}`
  }
  return undefined
}
