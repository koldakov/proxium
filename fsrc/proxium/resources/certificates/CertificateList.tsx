import { BooleanInput, DataTable, DateField, FunctionField, List } from 'react-admin'

import { ExpiresField } from '../../components/ExpiresField'
import { CertificateStatusChip } from './CertificateStatusChip'
import { describeCertificate } from './expiry'
import { TlsStatusAlert } from './TlsStatusAlert'

const filters = [<BooleanInput key="isActive" source="isActive" label="Active" />]

export const CertificateList = () => (
  <>
    <TlsStatusAlert />
    <List filters={filters} exporter={false}>
      <DataTable rowClick="show" bulkActionButtons={false}>
        <DataTable.Col source="id" disableSort />
        <DataTable.Col source="names" disableSort>
          <FunctionField render={describeCertificate} />
        </DataTable.Col>
        <DataTable.Col label="Status" disableSort>
          <CertificateStatusChip />
        </DataTable.Col>
        <DataTable.Col source="notValidAfter" label="Valid until" disableSort>
          <ExpiresField source="notValidAfter" />
        </DataTable.Col>
        <DataTable.Col source="createdAt" label="Added" disableSort>
          <DateField source="createdAt" showTime />
        </DataTable.Col>
      </DataTable>
    </List>
  </>
)
