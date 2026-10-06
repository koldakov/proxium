import { Link, useCreatePath, useRecordContext } from 'react-admin'

import { useDetailPage } from '../../components/detailPage'

/** The network in context as a link to its page, in a new tab: following it keeps the form as typed. */
export const NetworkLinkField = () => {
  const record = useRecordContext()
  const createPath = useCreatePath()
  const detailPage = useDetailPage('trusted-networks')
  if (record === undefined) {
    return null
  }

  return (
    <Link
      to={createPath({ resource: 'trusted-networks', id: record.id, type: detailPage })}
      target="_blank"
      rel="noopener"
    >
      {record.network}
    </Link>
  )
}
