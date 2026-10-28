import { Stack, Typography } from '@mui/material'
import { Title, useCanAccessResources } from 'react-admin'
import { Navigate } from 'react-router-dom'

import type { MenuNode } from '../../components/GroupedMenu'
import { menuTargets } from '../../components/menuTargets'
import { WIDGETS } from './widgets'

// Nothing to show here: the first page of the menu the user may open, as without the overview.
const FirstPage = ({ menu }: { menu: MenuNode[] }) => {
  const targets = menuTargets(menu).filter((target) => target.to !== '/')
  const { canAccess } = useCanAccessResources({
    action: 'list',
    resources: targets.flatMap((target) => target.resources),
  })
  if (canAccess === undefined) {
    return null
  }

  const target = targets.find((target) => target.resources.some((resource) => canAccess[resource]))
  if (target === undefined) {
    return (
      <Typography sx={{ mt: 2 }} color="text.secondary">
        Nothing here is open to you yet: ask an administrator for access.
      </Typography>
    )
  }
  return <Navigate to={target.to} replace />
}

/** How the proxy is doing at a glance, the start page. Blocks hide without access to them. */
export const OverviewPage = ({ menu }: { menu: MenuNode[] }) => {
  const { canAccess } = useCanAccessResources({
    action: 'list',
    resources: WIDGETS.map((widget) => widget.resource),
  })
  if (canAccess === undefined) {
    return null
  }

  const widgets = WIDGETS.filter((widget) => canAccess[widget.resource])
  if (widgets.length === 0) {
    return <FirstPage menu={menu} />
  }
  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <Title title="Overview" />
      {widgets.map(({ resource, component: Widget }) => (
        <Widget key={resource} />
      ))}
    </Stack>
  )
}
