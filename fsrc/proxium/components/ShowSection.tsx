import { Card, CardContent, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'

interface ShowSectionProps {
  title: string
  children: ReactNode
}

/** A titled block of fields on a show page. */
export const ShowSection = ({ title, children }: ShowSectionProps) => (
  <Card variant="outlined" sx={{ height: '100%' }}>
    <CardContent>
      <Typography variant="overline" color="text.secondary">
        {title}
      </Typography>
      <Stack spacing={2} sx={{ mt: 1 }}>
        {children}
      </Stack>
    </CardContent>
  </Card>
)
