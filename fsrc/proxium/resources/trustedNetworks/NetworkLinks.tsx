import { Fragment } from 'react'
import { Link, type RaRecord, useCreatePath } from 'react-admin'

import { useDetailPage } from '../../components/detailPage'

/** Networks as links to their pages, in a new tab: following one keeps the form as typed. */
export const NetworkLinks = ({ records }: { records: RaRecord[] }) => {
  const createPath = useCreatePath()
  const detailPage = useDetailPage('trusted-networks')

  return records.map((record, index) => (
    <Fragment key={record.id}>
      {index > 0 && ', '}
      <Link
        to={createPath({ resource: 'trusted-networks', id: record.id, type: detailPage })}
        target="_blank"
        rel="noopener"
      >
        {record.network} ({record.name})
      </Link>
    </Fragment>
  ))
}
