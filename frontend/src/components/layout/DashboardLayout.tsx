import React from "react";
import Header from "@/components/header/Header";

interface DashboardLayoutProps {
    children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-50 flex flex-col" suppressHydrationWarning>
            <Header />
            <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-[1600px] w-full mx-auto space-y-6" suppressHydrationWarning>
                {children}
            </main>
        </div>
    );
}
