import DashboardIcon from '@mui/icons-material/Dashboard'

import type { MenuLink } from '../../components/GroupedMenu'
import { WIDGETS } from './widgets'

export { OverviewPage } from './OverviewPage'

export const overviewLink: MenuLink = {
  to: '/',
  label: 'Overview',
  icon: DashboardIcon,
  resources: WIDGETS.map((widget) => widget.resource),
  // How the proxy is doing, apart from what the admin configures below.
  isSeparated: true,
  items: [{ resource: 'proxy-instances', label: 'Proxy instances' }],
}
