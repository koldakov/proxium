import DnsIcon from '@mui/icons-material/Dns'
import type { ResourceProps } from 'react-admin'

import { ProxyInstanceList } from './ProxyInstanceList'

export { ProxyInstancesOverview } from './ProxyInstancesOverview'

// List only: instances write themselves, the admin can only deregister them. In the menu under the overview.
export const proxyInstances: ResourceProps = {
  name: 'proxy-instances',
  options: { label: 'Proxy instances' },
  icon: DnsIcon,
  list: ProxyInstanceList,
  recordRepresentation: 'hostname',
}
