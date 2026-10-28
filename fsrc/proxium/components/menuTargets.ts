import type { MenuNode } from './GroupedMenu'

// A page the menu leads to and what the user may list to see it.
export interface MenuTarget {
  to: string
  resources: string[]
}

/** The pages of the menu in its order, e.g. to find the first one a user may open. */
export const menuTargets = (nodes: MenuNode[]): MenuTarget[] =>
  nodes.flatMap((node) => {
    if (typeof node === 'string') {
      return [{ to: `/${node}`, resources: [node] }]
    }
    const items = (node.items ?? []).map((item) => ({
      to: `/${item.resource}`,
      resources: [item.resource],
    }))
    if ('to' in node) {
      return [{ to: node.to, resources: node.resources }, ...items]
    }
    return items
  })
