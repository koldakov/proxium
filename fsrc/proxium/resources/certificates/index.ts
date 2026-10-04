import LockIcon from '@mui/icons-material/Lock'
import type { ResourceProps } from 'react-admin'

import { CertificateCreate } from './CertificateCreate'
import { CertificateList } from './CertificateList'
import { CertificateShow } from './CertificateShow'
import { describeCertificate } from './expiry'

// No edit page: a certificate can't change, only be activated, deactivated or deleted.
export const certificates: ResourceProps = {
  name: 'certificates',
  options: { label: 'TLS certificates' },
  icon: LockIcon,
  list: CertificateList,
  show: CertificateShow,
  create: CertificateCreate,
  recordRepresentation: describeCertificate,
}
