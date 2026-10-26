import type { FieldValues } from 'react-hook-form'

import { CONDITION_KINDS, PROTOCOLS, WEEKDAYS } from './conditions'
import { DIRECTIONS, QUOTA_DIRECTIONS } from './limits'

/** One-line summaries of a rule as the form holds it: what it applies to and what it limits. */

// How many items of a list a summary names before "+N".
const SHOWN_ITEMS = 2

const SCOPES: Record<string, string> = {
  identity: 'per account',
  client_ip: 'per client IP',
  target_host: 'per site',
  connection: 'per connection',
  global: 'whole proxy',
}

const nameOf = (choices: { id: string | number; name: string }[], id: unknown) =>
  choices.find((choice) => choice.id === id)?.name ?? String(id)

const splitList = (value: unknown) =>
  typeof value === 'string' ? value.split(/[\s,]+/).filter((item) => item !== '') : []

const shortList = (items: string[]) =>
  items.length <= SHOWN_ITEMS
    ? items.join(', ')
    : `${items.slice(0, SHOWN_ITEMS).join(', ')} +${items.length - SHOWN_ITEMS}`

/** Runs of weekdays as ranges: Mon–Fri, Sat, Sun. */
export const describeDays = (days: number[]) => {
  const sorted = [...new Set(days)].sort((a, b) => a - b)
  if (sorted.length === 7) {
    return 'Every day'
  }
  const runs: number[][] = []
  for (const day of sorted) {
    const run = runs.at(-1)
    if (run !== undefined && run.at(-1) === day - 1) {
      run.push(day)
    } else {
      runs.push([day])
    }
  }
  return runs
    .map((run) =>
      run.length > 2
        ? `${nameOf(WEEKDAYS, run[0])}–${nameOf(WEEKDAYS, run.at(-1))}`
        : run.map((day) => nameOf(WEEKDAYS, day)).join(', '),
    )
    .join(', ')
}

const describeBlock = (block: FieldValues) => {
  switch (block.kind) {
    case 'schedule':
      return `${describeDays(block.days ?? [])} ${block.start ?? '?'}–${block.end ?? '?'} ${block.timezone ?? ''}`.trim()
    case 'target_host':
      return `domain ${shortList(splitList(block.domains))}`
    case 'target_network':
      return `target IP ${shortList(splitList(block.networks))}`
    case 'client_network':
      return `client IP ${shortList(splitList(block.networks))}`
    case 'target_port':
      return `port ${shortList(splitList(block.ports))}`
    case 'protocol':
      return shortList(
        (block.protocols ?? []).map((id: string) => nameOf(PROTOCOLS, id).split(',')[0]),
      )
    case 'encrypted':
      return 'client uses TLS'
    default:
      return block.kind ? nameOf(CONDITION_KINDS, block.kind) : 'new condition'
  }
}

/** When the rule applies, e.g. "Mon–Fri 09:00–18:00 UTC and unless domain github.com". */
export const describeConditions = (rule: FieldValues) => {
  if (rule.complexCondition) {
    return 'Condition set through the API'
  }
  const blocks: FieldValues[] = rule.blocks ?? []
  if (blocks.length === 0) {
    return 'Always'
  }
  const joiner = rule.match === 'any' ? ' or ' : ' and '
  return blocks
    .map((block) => `${block.negate ? 'unless ' : ''}${describeBlock(block)}`)
    .join(joiner)
}

// Bytes as the form holds them, in the units the form shows.
const mbits = (bytesPerSecond: number) => `${(bytesPerSecond * 8) / 1_000_000} Mbit/s`
const gigabytes = (bytes: number) => `${bytes / 1_000_000_000} GB`

const describeQuotaPeriod = (quota: FieldValues) => {
  if (quota.period === 'total') {
    return 'in total'
  }
  const unit = quota.period === 'day' ? 'day' : 'month'
  return quota.periodLength > 1 ? `per ${quota.periodLength} ${unit}s` : `per ${unit}`
}

/** What the rule limits, e.g. "1 Mbit/s each way per account, 100 GB per month". */
export const describeLimits = (rule: FieldValues) => {
  const parts = [
    ...(rule.connectionLimits ?? []).map(
      (limit: FieldValues) =>
        `${limit.maxConnections ?? '?'} connections ${SCOPES[limit.scope] ?? ''}`,
    ),
    ...(rule.speedLimits ?? []).map(
      (limit: FieldValues) =>
        `${limit.rate ? mbits(limit.rate) : '? Mbit/s'} ${nameOf(DIRECTIONS, limit.direction).toLowerCase()} ${SCOPES[limit.scope] ?? ''}`,
    ),
    ...(rule.trafficQuotas ?? []).map(
      (quota: FieldValues) =>
        `${quota.maxBytes ? gigabytes(quota.maxBytes) : '? GB'} ${describeQuotaPeriod(quota)}${quota.direction === 'both' ? '' : `, ${nameOf(QUOTA_DIRECTIONS, quota.direction).toLowerCase()}`}`,
    ),
  ]
  return parts.length === 0 ? 'No limits' : parts.map((part) => part.trim()).join(', ')
}
