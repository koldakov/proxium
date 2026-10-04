import { FunctionField, ReferenceField, useCanAccess } from 'react-admin'

/** The user who created the record in context: linked with `users.view`, the bare id without it. */
export const CreatedByField = () => {
  const { canAccess, isPending } = useCanAccess({ resource: 'users', action: 'list' })
  if (isPending) {
    return null
  }

  return canAccess ? (
    <ReferenceField source="createdById" reference="users" link="show" />
  ) : (
    <FunctionField source="createdById" render={(record) => `#${record.createdById}`} />
  )
}
