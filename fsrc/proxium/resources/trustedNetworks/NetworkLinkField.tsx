import { Link, useCreatePath, useRecordContext } from 'react-admin'

/** The network in context as a link to its edit page, in a new tab: following it keeps the form as typed. */
export const NetworkLinkField = () => {
  const record = useRecordContext()
  const createPath = useCreatePath()
  if (record === undefined) {
    return null
  }

  return (
    <Link
      to={createPath({ resource: 'trusted-networks', id: record.id, type: 'edit' })}
      target="_blank"
      rel="noopener"
    >
      {record.network}
    </Link>
  )
}
