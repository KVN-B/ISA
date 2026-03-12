"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "ar", label: "العربية" },
  { code: "zh", label: "中文" },
  { code: "ru", label: "Русский" },
];

export default function Navigation() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const links = [
    { href: "/", label: "Dashboard" },
    { href: "/timeline", label: "Document Timeline" },
    { href: "/regulations", label: "Regulations" },
    { href: "/chat", label: "Ask a Question" },
  ];

  return (
    <nav className="text-white shadow-lg" style={{ background: "#003366" }}>
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="font-bold text-sm">
            ISA · Exploitation Regulations
          </Link>
          <div className="hidden md:flex gap-1">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  pathname === link.href
                    ? "bg-white bg-opacity-20 text-white"
                    : "text-white opacity-70 hover:opacity-100 hover:bg-white hover:bg-opacity-10"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Language selector */}
          <select
            className="bg-white bg-opacity-10 text-white text-xs border border-white border-opacity-20 rounded px-2 py-1 cursor-pointer"
            defaultValue="en"
            onChange={(e) => {
              // TODO: integrate with next-intl locale switching
              console.log("Language:", e.target.value);
            }}
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="text-gray-900">
                {l.label}
              </option>
            ))}
          </select>

          {/* Current doc badge */}
          <a
            href="https://isa.org.jm/wp-content/uploads/2026/02/Further-Revised-Consolidated-Text.pdf"
            target="_blank"
            rel="noopener noreferrer"
            className="hidden md:block text-xs bg-yellow-400 text-blue-900 font-bold px-3 py-1 rounded-full hover:bg-yellow-300"
          >
            ISBA/31/C/CRP.1/Rev.2 ↗
          </a>

          {/* Mobile menu */}
          <button
            className="md:hidden p-1"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Menu"
          >
            ☰
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden border-t border-white border-opacity-20 px-4 py-2">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="block py-2 text-sm opacity-80 hover:opacity-100"
              onClick={() => setMenuOpen(false)}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  );
}
