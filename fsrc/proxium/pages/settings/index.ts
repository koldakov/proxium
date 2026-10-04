import SettingsIcon from '@mui/icons-material/Settings'

import type { MenuLink } from '../../components/GroupedMenu'

export { SettingsPage } from './SettingsPage'

export const settingsLink: MenuLink = {
  to: '/settings',
  label: 'Settings',
  icon: SettingsIcon,
  resource: 'settings',
}
