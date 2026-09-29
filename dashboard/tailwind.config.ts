import type { Config } from 'tailwindcss';
import tailwindcssAnimate from 'tailwindcss-animate';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', '"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        pill: 'var(--radius-pill)',
        card: 'var(--radius-card)',
        input: 'var(--radius-input)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-input)',
        lg: 'var(--radius-card)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        float: 'var(--shadow-float)',
      },
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-muted': 'var(--surface-muted)',
        border: 'var(--border)',
        text: 'var(--text)',
        'text-body': 'var(--text-body)',
        'text-muted': 'var(--text-muted)',
        accent: 'var(--accent)',
        'accent-soft': 'var(--accent-soft)',
        success: 'var(--success)',
        warning: 'var(--warning)',
        danger: 'var(--danger)',
        background: 'var(--bg)',
        foreground: 'var(--text)',
        muted: 'var(--surface-muted)',
        'muted-foreground': 'var(--text-muted)',
        input: 'var(--border)',
        ring: 'var(--accent)',
        primary: 'var(--text)',
        'primary-foreground': '#ffffff',
        secondary: 'var(--surface)',
        'secondary-foreground': 'var(--text)',
        destructive: 'var(--danger)',
        'destructive-foreground': '#ffffff',
        'accent-foreground': 'var(--text)',
        popover: 'var(--surface)',
        'popover-foreground': 'var(--text)',
        card: 'var(--surface)',
        'card-foreground': 'var(--text)',
        'status-warning': 'var(--warning)',
        'status-success': 'var(--success)',
        'status-danger': 'var(--danger)',
      },
      maxWidth: {
        console: '1120px',
      },
      transitionDuration: {
        console: '150ms',
      },
    },
  },
  plugins: [tailwindcssAnimate],
};

export default config;
