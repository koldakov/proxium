import { Link, useCanAccess, useCreatePath } from 'react-admin'

/** Opens adding an outgoing IP in a new tab, so the form at hand keeps what is typed in it. */
export const AddOutgoingIPLink = () => {
  const createPath = useCreatePath()
  const { canAccess } = useCanAccess({ resource: 'outgoing-ips', action: 'create' })
  if (!canAccess) {
    return null
  }

  return (
    <Link to={createPath({ resource: 'outgoing-ips', type: 'create' })} target="_blank">
      Add an outgoing IP
    </Link>
  )
}
