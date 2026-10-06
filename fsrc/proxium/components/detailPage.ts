import { useCanAccess } from 'react-admin'

/** Where a record of `resource` opens: its edit page if the user may change it, its read-only page otherwise. */
export const useDetailPage = (resource: string): 'edit' | 'show' => {
  const { canAccess: canChange } = useCanAccess({ resource, action: 'edit' })
  return canChange ? 'edit' : 'show'
}
