import type { Metadata } from "next";
// Self-hosted brand typefaces (Nexa / Glacier substitutes from the design system) and a mono for codes.
import "@fontsource-variable/sora";
import "@fontsource-variable/outfit";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { ThemeProvider } from "@/components/theme-provider";

export const metadata: Metadata = {
  title: "Preduit",
  description: "Demand planning for B2B wholesale",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="scroll-smooth">
      <body className="min-h-screen bg-page font-sans text-fg-1 antialiased" suppressHydrationWarning>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
