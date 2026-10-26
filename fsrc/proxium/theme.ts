import '@fontsource-variable/inter'

import type { ChipProps } from '@mui/material'
import { alpha, type PaletteOptions, type Theme } from '@mui/material/styles'
import type { RaThemeOptions } from 'react-admin'

const lightPalette: PaletteOptions = {
  mode: 'light',
  primary: { main: '#6246ea' },
  secondary: { main: '#52525b' },
  success: { main: '#16a34a' },
  warning: { main: '#d97706' },
  error: { main: '#dc2626' },
  info: { main: '#0284c7' },
  // No pure white: large bright surfaces tire the eyes.
  background: { default: '#e1e3e8', paper: '#eceef1' },
  text: { primary: '#1f2329', secondary: '#626771' },
  divider: '#cdd0d7',
}

const darkPalette: PaletteOptions = {
  mode: 'dark',
  primary: { main: '#a394ff' },
  secondary: { main: '#a1a1aa' },
  success: { main: '#4ade80' },
  warning: { main: '#fbbf24' },
  error: { main: '#f87171' },
  info: { main: '#38bdf8' },
  background: { default: '#0e0e11', paper: '#17171b' },
  text: { primary: '#f4f4f5', secondary: '#a1a1aa' },
  divider: '#2a2a30',
}

// Same for both modes: colors come from the palette through `theme`.
const base: RaThemeOptions = {
  shape: { borderRadius: 8 },
  sidebar: { width: 240, closedWidth: 50 },
  typography: {
    fontFamily: '"Inter Variable", system-ui, sans-serif',
    fontSize: 14,
    h5: { fontWeight: 600, letterSpacing: '-0.01em' },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 500 },
    button: { textTransform: 'none', fontWeight: 500 },
    overline: { fontWeight: 600, letterSpacing: '0.08em', lineHeight: 2 },
  },
  components: {
    MuiAppBar: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        // Colors set here: react-admin passes color="secondary" over the default props.
        root: ({ theme }: { theme: Theme }) => ({
          color: theme.palette.text.primary,
          backgroundColor: alpha(theme.palette.background.default, 0.8),
          backdropFilter: 'blur(8px)',
          borderBottom: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none' },
        outlined: ({ theme }: { theme: Theme }) => ({ borderColor: theme.palette.divider }),
      },
    },
    MuiCard: {
      defaultProps: { variant: 'outlined' },
      styleOverrides: { root: { borderRadius: 12 } },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
    },
    MuiTextField: {
      defaultProps: { variant: 'outlined', margin: 'dense', size: 'small', fullWidth: true },
    },
    MuiFormControl: {
      defaultProps: { variant: 'outlined', margin: 'dense', size: 'small', fullWidth: true },
    },
    MuiAutocomplete: {
      defaultProps: { fullWidth: true },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: ({ theme }: { theme: Theme }) => ({
          backgroundColor: theme.palette.background.paper,
          '&:not(.Mui-focused):not(.Mui-error):hover .MuiOutlinedInput-notchedOutline': {
            borderColor: theme.palette.text.secondary,
          },
        }),
        notchedOutline: ({ theme }: { theme: Theme }) => ({ borderColor: theme.palette.divider }),
      },
    },
    MuiChip: {
      styleOverrides: {
        root: ({ theme, ownerState }: { theme: Theme; ownerState: ChipProps }) => {
          const { color = 'default', variant = 'filled' } = ownerState
          const base = { borderRadius: 6, fontWeight: 500 }
          if (color === 'default' || variant !== 'filled') {
            return base
          }
          // Soft: colored text on a tint of the same color instead of a solid fill.
          const main = theme.palette[color].main
          return {
            ...base,
            color: theme.palette.mode === 'light' ? theme.palette[color].dark : main,
            backgroundColor: alpha(main, 0.16),
          }
        },
      },
    },
    MuiTooltip: {
      defaultProps: { arrow: true },
    },
    MuiTableCell: {
      styleOverrides: {
        root: ({ theme }: { theme: Theme }) => ({ borderBottomColor: theme.palette.divider }),
        head: ({ theme }: { theme: Theme }) => ({
          color: theme.palette.text.secondary,
          fontSize: '0.75rem',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          backgroundColor: theme.palette.background.default,
        }),
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: { '&:last-child td': { borderBottom: 0 } },
      },
    },
    MuiToggleButton: {
      styleOverrides: { root: { textTransform: 'none' } },
    },
    MuiTab: {
      styleOverrides: { root: { textTransform: 'none' } },
    },
    RaLayout: {
      styleOverrides: {
        root: ({ theme }: { theme: Theme }) => ({
          '& .RaLayout-content': { padding: theme.spacing(3) },
        }),
      },
    },
    RaMenuItemLink: {
      styleOverrides: {
        root: ({ theme }: { theme: Theme }) => ({
          // A pill only in the open sidebar: the closed one is as wide as an icon.
          '.RaSidebar-open &': {
            margin: theme.spacing(0.25, 1),
            borderRadius: theme.shape.borderRadius,
          },
          '&.RaMenuItemLink-active': {
            color: theme.palette.primary.main,
            backgroundColor: alpha(theme.palette.primary.main, 0.1),
            fontWeight: 600,
            '& .MuiSvgIcon-root': { color: theme.palette.primary.main },
          },
        }),
      },
    },
    RaToolbar: {
      styleOverrides: {
        root: ({ theme }: { theme: Theme }) => ({
          backgroundColor: 'transparent',
          borderTop: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
    RaNotification: {
      defaultProps: { anchorOrigin: { vertical: 'top', horizontal: 'center' } },
      styleOverrides: {
        // A dark pill in both modes, the kind told by a colored dot instead of a filled background.
        root: ({ theme }: { theme: Theme }) => {
          const isLight = theme.palette.mode === 'light'
          const surface = { backgroundColor: isLight ? '#1f2329' : '#2a2a31', color: '#f4f5f7' }
          const dot = (color: string) => ({
            ...surface,
            '& .MuiSnackbarContent-message::before': { backgroundColor: color },
          })
          // Under the app bar, MUI puts it at its top edge.
          const top = { top: theme.spacing(8) }
          return {
            ...top,
            [theme.breakpoints.up('sm')]: top,
            '& .MuiSnackbarContent-root': {
              ...surface,
              minWidth: 0,
              borderRadius: 10,
              fontWeight: 500,
              boxShadow: theme.shadows[8],
              border: isLight ? 'none' : `1px solid ${theme.palette.divider}`,
            },
            '& .MuiSnackbarContent-message': {
              display: 'flex',
              alignItems: 'center',
              gap: theme.spacing(1.25),
              '&::before': {
                content: '""',
                width: 8,
                height: 8,
                flexShrink: 0,
                borderRadius: '50%',
                backgroundColor: theme.palette.info.main,
              },
            },
            '& .RaNotification-success': dot(theme.palette.success.main),
            '& .RaNotification-warning': dot(theme.palette.warning.main),
            '& .RaNotification-error': dot(theme.palette.error.main),
          }
        },
      },
    },
    RaSimpleFormIterator: {
      defaultProps: { fullWidth: true },
    },
  },
}

export const lightTheme: RaThemeOptions = { ...base, palette: lightPalette }
export const darkTheme: RaThemeOptions = { ...base, palette: darkPalette }
