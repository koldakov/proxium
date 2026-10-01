import { Link, useCreatePath } from 'react-admin'

/** Opens adding an outgoing IP in a new tab, so the form at hand keeps what is typed in it. */
export const AddOutgoingIPLink = () => {
  const createPath = useCreatePath()

  return (
    <Link to={createPath({ resource: 'outgoing-ips', type: 'create' })} target="_blank">
      Add an outgoing IP
    </Link>
  )
}
