import type { ComponentType } from 'react'

import { OutgoingIPsOverview } from '../../resources/outgoingIps'
import { ProxyInstancesOverview } from '../../resources/proxyInstances'

export interface OverviewWidget {
  // Shown if the user may list it.
  resource: string
  component: ComponentType
}

// The overview, in order: a new block is one more entry here.
export const WIDGETS: OverviewWidget[] = [
  { resource: 'proxy-instances', component: ProxyInstancesOverview },
  { resource: 'outgoing-ips', component: OutgoingIPsOverview },
]
