import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Collapse,
  Divider,
  IconButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Stack,
} from '@mui/material'
import { type ComponentType, useState } from 'react'
import { Menu, useCanAccessResources, useSidebarState } from 'react-admin'
import { useLocation } from 'react-router-dom'

export interface MenuGroupItem {
  resource: string
  // Shorter than the resource label, the group gives the context.
  label: string
}

export interface MenuGroup {
  label: string
  icon: ComponentType
  items: MenuGroupItem[]
}

// A page that isn't a resource, e.g. settings. Shown if the user may list any of `resources`.
export interface MenuLink {
  to: string
  label: string
  icon: ComponentType
  resources: string[]
  // Set apart from the items below, e.g. the start page.
  isSeparated?: boolean
  // Pages under it, folded until opened or one of them is.
  items?: MenuGroupItem[]
}

// A resource name for a top-level item, a collapsible group of them, or a link to another page.
export type MenuNode = string | MenuGroup | MenuLink

const SubItems = ({ items, open }: { items: MenuGroupItem[]; open: boolean }) => {
  const [sidebarOpen] = useSidebarState()

  return (
    <Collapse in={open} timeout="auto" unmountOnExit>
      {/* Indented only when labels are shown: a closed sidebar has icons alone. */}
      <div style={sidebarOpen ? { paddingLeft: 16 } : undefined}>
        {items.map((item) => (
          <Menu.ResourceItem key={item.resource} name={item.resource} primaryText={item.label} />
        ))}
      </div>
    </Collapse>
  )
}

const Group = ({ label, icon: Icon, items }: MenuGroup) => {
  const [open, setOpen] = useState(true)
  const [sidebarOpen] = useSidebarState()
  // The items hide themselves, the group goes with the last of them.
  const { canAccess } = useCanAccessResources({
    action: 'list',
    resources: items.map((item) => item.resource),
  })
  if (canAccess === undefined || !Object.values(canAccess).some(Boolean)) {
    return null
  }

  return (
    <>
      <MenuItem
        onClick={() => setOpen(!open)}
        // In line with the links: they are pills in the open sidebar, see the theme.
        sx={[{ color: 'text.secondary' }, sidebarOpen && { mx: 1, my: 0.25, borderRadius: 1 }]}
      >
        <ListItemIcon sx={{ minWidth: 40, color: 'text.secondary' }}>
          <Icon />
        </ListItemIcon>
        <ListItemText>{label}</ListItemText>
        {sidebarOpen && (open ? <ExpandLessIcon /> : <ExpandMoreIcon />)}
      </MenuItem>
      <SubItems items={items} open={open} />
    </>
  )
}

const Link = ({ to, label, icon: Icon, resources, isSeparated, items = [] }: MenuLink) => {
  // Unset follows the page: open on one of the items, folded elsewhere. A click on the arrow decides from then on.
  const [open, setOpen] = useState<boolean>()
  const [sidebarOpen] = useSidebarState()
  const { pathname } = useLocation()
  const { canAccess } = useCanAccessResources({ action: 'list', resources })
  if (canAccess === undefined || !Object.values(canAccess).some(Boolean)) {
    return null
  }

  const isOnItem = items.some(
    (item) => pathname === `/${item.resource}` || pathname.startsWith(`/${item.resource}/`),
  )
  const isOpen = open ?? isOnItem
  return (
    <>
      <Menu.Item to={to} primaryText={label} leftIcon={<Icon />}>
        {items.length > 0 && sidebarOpen ? (
          <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
            {label}
            <IconButton
              size="small"
              edge="end"
              aria-label={isOpen ? `Fold ${label}` : `Unfold ${label}`}
              onClick={(event) => {
                // Inside the link: the arrow only folds, it doesn't open the page.
                event.preventDefault()
                event.stopPropagation()
                setOpen(!isOpen)
              }}
            >
              {isOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Stack>
        ) : undefined}
      </Menu.Item>
      <SubItems items={items} open={isOpen} />
      {/* Hidden with the link: no stray line atop the menu. */}
      {isSeparated && <Divider sx={{ my: 1.5 }} />}
    </>
  )
}

const Node = ({ node }: { node: MenuNode }) => {
  if (typeof node === 'string') {
    return <Menu.ResourceItem name={node} />
  }
  if ('to' in node) {
    return <Link {...node} />
  }
  return <Group {...node} />
}

/** The sidebar menu from a list of resources, groups and links, in the given order. */
export const GroupedMenu = ({ nodes }: { nodes: MenuNode[] }) => (
  <Menu>
    {nodes.map((node) => (
      <Node key={typeof node === 'string' ? node : node.label} node={node} />
    ))}
  </Menu>
)
