import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { Collapse, ListItemIcon, ListItemText, MenuItem } from '@mui/material'
import { type ComponentType, useState } from 'react'
import { Menu, useSidebarState } from 'react-admin'

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

// A page that isn't a resource, e.g. settings.
export interface MenuLink {
  to: string
  label: string
  icon: ComponentType
}

// A resource name for a top-level item, a collapsible group of them, or a link to another page.
export type MenuNode = string | MenuGroup | MenuLink

const Group = ({ label, icon: Icon, items }: MenuGroup) => {
  const [open, setOpen] = useState(true)
  const [sidebarOpen] = useSidebarState()

  return (
    <>
      <MenuItem onClick={() => setOpen(!open)} sx={{ color: 'text.secondary' }}>
        <ListItemIcon sx={{ minWidth: 40, color: 'text.secondary' }}>
          <Icon />
        </ListItemIcon>
        <ListItemText>{label}</ListItemText>
        {sidebarOpen && (open ? <ExpandLessIcon /> : <ExpandMoreIcon />)}
      </MenuItem>
      <Collapse in={open} timeout="auto" unmountOnExit>
        {/* Indented only when labels are shown: a closed sidebar has icons alone. */}
        <div style={sidebarOpen ? { paddingLeft: 16 } : undefined}>
          {items.map((item) => (
            <Menu.ResourceItem key={item.resource} name={item.resource} primaryText={item.label} />
          ))}
        </div>
      </Collapse>
    </>
  )
}

const Node = ({ node }: { node: MenuNode }) => {
  if (typeof node === 'string') {
    return <Menu.ResourceItem name={node} />
  }
  if ('to' in node) {
    const { to, label, icon: Icon } = node
    return <Menu.Item to={to} primaryText={label} leftIcon={<Icon />} />
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
