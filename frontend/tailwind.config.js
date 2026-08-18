/** @type {import('tailwindcss').Config} */
function withOpacity(variable) {
  return `rgb(var(${variable}) / <alpha-value>)`
}

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: withOpacity('--color-bg'),
        surface: withOpacity('--color-surface'),
        'surface-2': withOpacity('--color-surface-2'),
        'surface-hover': withOpacity('--color-surface-hover'),
        border: withOpacity('--color-border'),
        'border-strong': withOpacity('--color-border-strong'),
        text: withOpacity('--color-text'),
        'text-muted': withOpacity('--color-text-muted'),
        'text-faint': withOpacity('--color-text-faint'),
        accent: withOpacity('--color-accent'),
        'accent-hover': withOpacity('--color-accent-hover'),
        data: withOpacity('--color-data'),
        success: withOpacity('--color-success'),
        warning: withOpacity('--color-warning'),
        danger: withOpacity('--color-danger'),
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['"Source Serif 4"', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', '"SF Mono"', 'monospace'],
      },
      keyframes: {
        'fade-in-up': {
          from: { opacity: 0, transform: 'translateY(6px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.22s ease-out',
      },
    },
  },
  plugins: [],
}
