import type { Config } from "tailwindcss";

const config: Config = {
    darkMode: ["class"],
    content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
  	extend: {
  		fontFamily: {
  			sans: ['var(--font-ui)', 'Outfit', 'system-ui', 'sans-serif'],
  			display: ['var(--font-display)', 'Sora', 'system-ui', 'sans-serif'],
  			mono: ['var(--font-mono)', 'ui-monospace', 'monospace']
  		},
  		boxShadow: {
  			card: 'var(--shadow-sm)',
  			lift: 'var(--shadow-md)',
  			brand: 'var(--shadow-primary)'
  		},
  		colors: {
  			page: 'var(--page)',
  			soft: 'var(--soft)',
  			line: 'var(--line)',
  			chrome: 'var(--chrome)',
  			champagne: 'var(--champagne)',
  			'fg-1': 'var(--fg-1)',
  			'fg-2': 'var(--fg-2)',
  			'fg-3': 'var(--fg-3)',
  			'fg-4': 'var(--neutral-400)',
  			'border-strong': 'var(--border-strong)',
  			brand: {
  				DEFAULT: 'var(--brand)',
  				hover: 'var(--brand-hover)',
  				soft: 'var(--brand-soft)',
  				'50': 'var(--orange-50)',
  				'200': 'var(--orange-200)',
  				'700': 'var(--orange-700)',
  				'800': 'var(--orange-800)',
  				tile: 'var(--orange-tile)'
  			},
  			success: {
  				'50': 'var(--green-50)',
  				'400': 'var(--green-400)',
  				'600': 'var(--green-600)'
  			},
  			plum: {
  				'50': 'var(--purple-50)',
  				'600': 'var(--purple-600)'
  			},
  			danger: {
  				DEFAULT: 'var(--danger)',
  				soft: 'var(--danger-soft)'
  			},
  			background: 'var(--background)',
  			foreground: 'var(--foreground)',
  			card: {
  				DEFAULT: 'var(--card)',
  				foreground: 'var(--card-foreground)'
  			},
  			popover: {
  				DEFAULT: 'var(--popover)',
  				foreground: 'var(--popover-foreground)'
  			},
  			primary: {
  				DEFAULT: 'var(--primary)',
  				foreground: 'var(--primary-foreground)'
  			},
  			secondary: {
  				DEFAULT: 'var(--secondary)',
  				foreground: 'var(--secondary-foreground)'
  			},
  			muted: {
  				DEFAULT: 'var(--muted)',
  				foreground: 'var(--muted-foreground)'
  			},
  			accent: {
  				DEFAULT: 'var(--accent)',
  				foreground: 'var(--accent-foreground)'
  			},
        destructive: {DEFAULT:'var(--destructive)',foreground:'var(--destructive-foreground)'},
  			border: 'var(--border)',
  			input: 'var(--input)',
  			ring: 'var(--ring)',
  			chart: {
  				'1': 'var(--chart-1)',
  				'2': 'var(--chart-2)',
  				'3': 'var(--chart-3)',
  				'4': 'var(--chart-4)',
  				'5': 'var(--chart-5)'
  			},
  			sidebar: {
  				DEFAULT: 'var(--sidebar)',
  				foreground: 'var(--sidebar-foreground)',
  				primary: 'var(--sidebar-primary)',
  				'primary-foreground': 'var(--sidebar-primary-foreground)',
  				accent: 'var(--sidebar-accent)',
  				'accent-foreground': 'var(--sidebar-accent-foreground)',
  				border: 'var(--sidebar-border)',
  				ring: 'var(--sidebar-ring)'
  			}
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
