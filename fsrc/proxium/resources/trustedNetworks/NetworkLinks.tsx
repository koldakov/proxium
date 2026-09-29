import { Fragment } from 'react'
import { Link, type RaRecord, useCreatePath } from 'react-admin'

/** Networks as links to their edit pages, in a new tab: following one keeps the form as typed. */
export const NetworkLinks = ({ records }: { records: RaRecord[] }) => {
  const createPath = useCreatePath()

  return records.map((record, index) => (
    <Fragment key={record.id}>
      {index > 0 && ', '}
      <Link
        to={createPath({ resource: 'trusted-networks', id: record.id, type: 'edit' })}
        target="_blank"
        rel="noopener"
      >
        {record.network} ({record.name})
      </Link>
    </Fragment>
  ))
}
