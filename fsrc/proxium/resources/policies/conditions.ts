import type { RaRecord } from 'react-admin'

import { ipNetwork } from '../../components/validators'

/**
 * The API stores a rule's condition as a tree of blocks. The form edits the common shape of it: a list of checks
 * that must all match or any one, each may be negated. A deeper tree, set through the API, is kept as is.
 */

export const CONDITION_KINDS = [
  { id: 'schedule', name: 'Time' },
  { id: 'target_host', name: 'Target domain' },
  { id: 'target_network', name: 'Target IP' },
  { id: 'target_port', name: 'Target port' },
  { id: 'protocol', name: 'Protocol' },
  { id: 'client_network', name: 'Client IP' },
  { id: 'encrypted', name: 'Client uses TLS' },
]

export const CONDITION_MATCHES = [
  { id: 'all', name: 'All conditions match' },
  { id: 'any', name: 'Any condition matches' },
]

// ISO weekdays, as the API takes them.
export const WEEKDAYS = [
  { id: 1, name: 'Mon' },
  { id: 2, name: 'Tue' },
  { id: 3, name: 'Wed' },
  { id: 4, name: 'Thu' },
  { id: 5, name: 'Fri' },
  { id: 6, name: 'Sat' },
  { id: 7, name: 'Sun' },
]

export const PROTOCOLS = [
  { id: 'http', name: 'HTTP' },
  { id: 'http-connect', name: 'HTTP CONNECT, e.g. HTTPS' },
  { id: 'socks5', name: 'SOCKS5' },
]

// Some browsers leave UTC out of the list.
export const TIME_ZONES = [...new Set(['UTC', ...Intl.supportedValuesOf('timeZone')])].map(
  (zone) => ({
    id: zone,
    name: zone,
  }),
)

export const browserTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone

const LEAF_KINDS = new Set(CONDITION_KINDS.map((kind) => kind.id))

type Condition = { kind: string; [field: string]: unknown }

/** One check as the form edits it: lists as text, one item per line or comma. */
type FormBlock = { kind: string; negate: boolean; [field: string]: unknown }

const splitList = (value: unknown) =>
  typeof value === 'string' ? value.split(/[\s,]+/).filter((item) => item !== '') : []

const toPortsText = (ports: { first: number; last: number }[]) =>
  ports.map(({ first, last }) => (first === last ? `${first}` : `${first}-${last}`)).join(', ')

const parsePorts = (value: unknown) =>
  splitList(value).map((item) => {
    const [first, last = first] = item.split('-').map(Number)
    return { first, last }
  })

// The API sends times with seconds, the time input takes HH:MM.
const toTimeText = (value: unknown) => (typeof value === 'string' ? value.slice(0, 5) : value)

const toFormBlock = (condition: Condition, negate: boolean): FormBlock => {
  const block: FormBlock = { ...condition, negate }
  switch (condition.kind) {
    case 'target_host':
      block.domains = (condition.domains as string[]).join('\n')
      break
    case 'target_network':
    case 'client_network':
      block.networks = (condition.networks as string[]).join('\n')
      break
    case 'target_port':
      block.ports = toPortsText(condition.ports as { first: number; last: number }[])
      break
    case 'schedule':
      block.start = toTimeText(condition.start)
      block.end = toTimeText(condition.end)
      break
  }
  return block
}

const toApiLeaf = ({ negate, ...block }: FormBlock): Condition => {
  const leaf: Condition = { ...block }
  switch (block.kind) {
    case 'target_host':
      leaf.domains = splitList(block.domains)
      break
    case 'target_network':
    case 'client_network':
      leaf.networks = splitList(block.networks)
      break
    case 'target_port':
      leaf.ports = parsePorts(block.ports)
      break
  }
  return negate ? { kind: 'not', condition: leaf } : leaf
}

/** A leaf, maybe negated, as one form block. Null if it's anything deeper. */
const toSingleBlock = (condition: Condition): FormBlock | null => {
  if (LEAF_KINDS.has(condition.kind)) {
    return toFormBlock(condition, false)
  }
  const inner = condition.condition as Condition | undefined
  if (condition.kind === 'not' && inner && LEAF_KINDS.has(inner.kind)) {
    return toFormBlock(inner, true)
  }
  return null
}

/** The form fields of a rule's condition: `match` and `blocks`, or `complexCondition` the form can't edit. */
const toFormCondition = (condition: Condition) => {
  if (condition.kind === 'always') {
    return { match: 'all', blocks: [] }
  }
  const single = toSingleBlock(condition)
  if (single) {
    return { match: 'all', blocks: [single] }
  }
  if (condition.kind === 'all' || condition.kind === 'any') {
    const blocks = (condition.conditions as Condition[]).map(toSingleBlock)
    if (blocks.every((block) => block !== null)) {
      return { match: condition.kind, blocks }
    }
  }
  return { match: 'all', blocks: [], complexCondition: condition }
}

/** A rule's form fields as the API condition. */
export const toApiCondition = (rule: {
  match?: string
  blocks?: FormBlock[]
  complexCondition?: Condition
}): Condition => {
  if (rule.complexCondition) {
    return rule.complexCondition
  }
  const blocks = rule.blocks ?? []
  if (blocks.length === 0) {
    return { kind: 'always' }
  }
  if (blocks.length === 1) {
    return toApiLeaf(blocks[0])
  }
  return { kind: rule.match ?? 'all', conditions: blocks.map(toApiLeaf) }
}

/** The policy as the form edits it: each rule's condition split into form fields. */
export const toFormPolicy = (record: RaRecord) => ({
  ...record,
  rules: (record.rules ?? []).map(({ condition, ...rule }: RaRecord) => ({
    ...rule,
    ...toFormCondition(condition),
  })),
})

export const LIST_HELPER = 'One per line or separated by commas'

/** At least one item, each passing `check`, which returns an error or nothing. */
const listOf = (check: (item: string) => string | undefined) => (value: unknown) => {
  const items = splitList(value)
  if (items.length === 0) {
    return 'Required'
  }
  for (const item of items) {
    const error = check(item)
    if (error) {
      return `${item}: ${error}`
    }
  }
  return undefined
}

const checkNetwork = ipNetwork()

export const networksList = () => listOf((item) => checkNetwork(item))

// Letters, digits, hyphens and dots, or any letters of an internationalized name.
const DOMAIN = /^[\p{L}\p{N}-]+(\.[\p{L}\p{N}-]+)*\.?$/u

export const domainsList = () =>
  listOf((item) => (DOMAIN.test(item) ? undefined : 'Must be a domain like example.com'))

const PORT_RANGE = /^(\d+)(?:-(\d+))?$/

export const portsList = () =>
  listOf((item) => {
    const match = PORT_RANGE.exec(item)
    if (!match) {
      return 'Must be a port like 443 or a range like 8000-8999'
    }
    const first = Number(match[1])
    const last = Number(match[2] ?? match[1])
    if (first < 1 || last > 65535) {
      return 'Ports go from 1 to 65535'
    }
    return first > last ? 'The range starts after it ends' : undefined
  })
