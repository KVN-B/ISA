import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import Navigation from "@/components/Navigation";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ISA Exploitation Regulations | International Seabed Authority",
  description:
    "Open platform for the development of exploitation regulations for mineral resources in the Area. ISBA/31/C/CRP.1/Rev.2",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} dir={locale === "ar" ? "rtl" : "ltr"}>
      <body className={inter.className}>
        <NextIntlClientProvider messages={messages}>
          <Navigation />
          <main className="min-h-screen bg-slate-50">{children}</main>
          <footer className="bg-isa-blue text-white py-6 px-8 text-center text-sm">
            <p>
              International Seabed Authority ·{" "}
              <a
                href="https://www.isa.org.jm"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-isa-gold"
              >
                isa.org.jm
              </a>
            </p>
            <p className="mt-1 opacity-60 text-xs">
              Open-source platform ·{" "}
              <a
                href="https://github.com/KVN-B/ISA"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                github.com/KVN-B/ISA
              </a>
            </p>
          </footer>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
